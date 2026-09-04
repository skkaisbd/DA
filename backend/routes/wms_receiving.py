"""
WMS — Receiving Layer (Inbound/Outbound Pending Queue + Scan-in/Scan-out)
Phase 1: Flow Control

Flow:
  INBOUND (FG dari Produksi):
    Production WO selesai → POST /wms/pending (type=inbound, source=production)
    Stok FG BELUM bertambah sampai scan-in dikonfirmasi
    Warehouse scan: POST /wms/pending/{id}/scan-in → stok FG bertambah

  OUTBOUND RM (Material Issue ke Produksi):
    Production request material → POST /wms/pending (type=outbound_rm, source=material_issue)
    Stok RM BELUM berkurang sampai scan-out
    Warehouse scan: POST /wms/pending/{id}/scan-out → stok RM berkurang

  INBOUND manual (PO received):
    POST /wms/pending (type=inbound, source=purchase_order)

  OUTBOUND manual (Shipment FG):
    Shipment created → POST /wms/pending (type=outbound_fg, source=shipment)
    Stok FG BELUM berkurang sampai scan-out
    Warehouse scan: POST /wms/pending/{id}/scan-out → stok FG berkurang

Collection:
  wh_pending_movements:
    id, ref_number, type (inbound|outbound_rm|outbound_fg),
    source_type (production|shipment|purchase_order|manual|material_issue),
    source_id, source_ref,
    material_id, material_code, material_name, material_type (rm|fg|wip),
    expected_qty, unit,
    scanned_qty, position_id, barcode_scanned,
    building_id, zone_id, rack_id,
    status (pending|partial|confirmed|cancelled),
    created_at, created_by, confirmed_at, confirmed_by

Routes:
  GET    /api/wms/pending          — list pending movements
  POST   /api/wms/pending          — create manual pending movement
  GET    /api/wms/pending/summary  — counts: pending_in, pending_out, partial
  POST   /api/wms/pending/{id}/scan-in   — confirm inbound (adds stock)
  POST   /api/wms/pending/{id}/scan-out  — confirm outbound (reduces stock)
  POST   /api/wms/pending/{id}/cancel    — cancel pending
  POST   /api/wms/pending/create-from-production — called by production portal
  POST   /api/wms/pending/create-from-shipment   — called by shipment portal
"""

import uuid
import logging
from datetime import datetime, timezone
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Request, Query
from pydantic import BaseModel, Field
from database import get_db
from auth import require_auth, serialize_doc, log_activity
from utils.counters import next_counter
from core.stock_schema import inc_all_qty, read_qty, set_all_qty
from core import stock_service
from core import uom as _uom  # SSOT konversi satuan
from core import bom_uom as _bom_uom  # cakupan konversi lebar (kemasan + global + kain)

router = APIRouter(prefix="/api/wms", tags=["wms-receiving"])


def _uid(): return str(uuid.uuid4())
def _now(): return datetime.now(timezone.utc)
def _counter_prefix(t): return {"inbound": "RCV", "outbound_rm": "IRM", "outbound_fg": "IFG"}.get(t, "MOV")


async def _next_ref(db, prefix: str) -> str:
    seq = await next_counter(db, prefix, namespace="wms")
    return f"{prefix}-{seq:05d}"


# ══════════════════════════════════════════════════════════════════════════════
# PYTHON HELPERS — callable from other backend modules (NOT HTTP)
# ══════════════════════════════════════════════════════════════════════════════

async def helper_create_pending_inbound_fg(
    db, *, material_id: str, material_code: str, material_name: str,
    qty: float, unit: str = "pcs",
    source_type: str = "production", source_id: str = "",
    source_ref: str = "", building_id: str = "", notes: str = "",
    created_by: str = "system",
) -> dict:
    """
    Internal helper (non-HTTP). Creates a PENDING INBOUND movement for FG.
    Called from rahaza_bundles (WO completion) and rahaza_production (PACKING).
    Returns the created movement document (or existing if duplicate for same source).
    """
    # Dedupe per-source (don't create multiple pendings for same WO/event)
    if source_id:
        existing = await db.wh_pending_movements.find_one({
            "source_id": source_id, "source_type": source_type,
            "type": "inbound",
            "status": {"$in": ["pending", "partial"]},
        }, {"_id": 0})
        if existing:
            # If same qty, just return. If different (e.g., additional packing output), create new.
            if abs(existing.get("expected_qty", 0) - qty) < 0.001:
                return existing

    ref = await _next_ref(db, "RCV")
    doc = {
        "id": _uid(), "ref_number": ref,
        "type": "inbound", "source_type": source_type,
        "source_id": source_id or "", "source_ref": source_ref or "",
        "material_id": material_id, "material_code": material_code,
        "material_name": material_name, "material_type": "fg",
        "expected_qty": qty, "scanned_qty": 0,
        "unit": unit,
        "building_id": building_id or "",
        "position_id": None, "position_barcode": None,
        "status": "pending", "notes": notes,
        "created_at": _now(), "created_by": created_by,
        "confirmed_at": None, "confirmed_by": None,
    }
    await db.wh_pending_movements.insert_one(dict(doc))
    return doc


async def helper_create_pending_outbound_fg(
    db, *, material_id: str, material_code: str, material_name: str,
    qty: float, unit: str = "pcs",
    source_type: str = "shipment", source_id: str = "",
    source_ref: str = "", building_id: str = "", notes: str = "",
    created_by: str = "system",
    dedupe: bool = False, extra: Optional[dict] = None,
) -> dict:
    """
    Internal helper. Creates PENDING OUTBOUND_FG — stock NOT reduced until scan-out.
    Called from rahaza_shipments dispatch & fulfillment dispatch.
    `dedupe=True` menghindari duplikat pending untuk (source_id, source_type, material_id) yang sama.
    `extra` di-merge ke dokumen (mis. stock_id, location_id untuk alur fulfillment).
    """
    if dedupe and source_id:
        existing = await db.wh_pending_movements.find_one({
            "source_id": source_id, "source_type": source_type,
            "type": "outbound_fg", "material_id": material_id,
            "status": {"$in": ["pending", "partial"]},
        }, {"_id": 0})
        if existing:
            return existing

    ref = await _next_ref(db, "IFG")
    doc = {
        "id": _uid(), "ref_number": ref,
        "type": "outbound_fg", "source_type": source_type,
        "source_id": source_id or "", "source_ref": source_ref or "",
        "material_id": material_id, "material_code": material_code,
        "material_name": material_name, "material_type": "fg",
        "expected_qty": qty, "scanned_qty": 0,
        "unit": unit,
        "building_id": building_id or "",
        "position_id": None, "position_barcode": None,
        "status": "pending", "notes": notes,
        "created_at": _now(), "created_by": created_by,
        "confirmed_at": None, "confirmed_by": None,
    }
    if extra:
        doc.update(extra)
    await db.wh_pending_movements.insert_one(dict(doc))
    return doc


async def helper_create_pending_outbound_rm(
    db, *, material_id: str, material_code: str, material_name: str,
    qty: float, unit: str = "pcs",
    source_type: str = "material_issue", source_id: str = "",
    source_ref: str = "", building_id: str = "", notes: str = "",
    created_by: str = "system",
) -> dict:
    """
    Internal helper. Creates PENDING OUTBOUND_RM — stock NOT reduced until scan-out.
    Called from dewi_maklon material-issues and any raw material request.
    """
    # Dedupe per-source
    if source_id:
        existing = await db.wh_pending_movements.find_one({
            "source_id": source_id, "source_type": source_type,
            "type": "outbound_rm",
            "status": {"$in": ["pending", "partial"]},
        }, {"_id": 0})
        if existing:
            return existing

    ref = await _next_ref(db, "IRM")
    doc = {
        "id": _uid(), "ref_number": ref,
        "type": "outbound_rm", "source_type": source_type,
        "source_id": source_id or "", "source_ref": source_ref or "",
        "material_id": material_id, "material_code": material_code,
        "material_name": material_name, "material_type": "rm",
        "expected_qty": qty, "scanned_qty": 0,
        "unit": unit,
        "building_id": building_id or "",
        "position_id": None, "position_barcode": None,
        "status": "pending", "notes": notes,
        "created_at": _now(), "created_by": created_by,
        "confirmed_at": None, "confirmed_by": None,
    }
    await db.wh_pending_movements.insert_one(dict(doc))
    return doc


async def helper_check_rack_occupancy_alert(db, rack_id: str) -> Optional[dict]:
    """
    Dicek setelah setiap scan-in / opname adjust yang mengubah occupancy rak.
    Jika rak naik ke >= 95% (kritis), buat notifikasi ke warehouse_manager
    (role 'warehouse_manager' atau 'owner' atau 'supervisor').
    Returns {"alert": dict, "created": bool} — created=True kalau alert baru dibuat,
    created=False kalau sudah ada alert aktif (<24h) untuk rak ini.
    Returns None kalau rak tidak perlu alert.
    """
    rack = await db.wh_racks.find_one({"id": rack_id}, {"_id": 0})
    if not rack:
        return None
    total = (rack.get("num_shelves") or 0) * (rack.get("slots_per_shelf") or 0)
    if total <= 0:
        return None
    occupied = await db.wh_positions.count_documents({"rack_id": rack_id, "status": "occupied"})
    pct = round(occupied / total * 100) if total else 0
    if pct < 95:
        return None

    # Dedupe: skip if active alert < 24h
    from datetime import timedelta
    cutoff = _now() - timedelta(hours=24)
    existing = await db.wh_rack_alerts.find_one({
        "rack_id": rack_id,
        "severity": "critical",
        "created_at": {"$gte": cutoff},
    }, {"_id": 0})
    if existing:
        return {"alert": existing, "created": False}

    alert_id = _uid()
    alert_doc = {
        "id": alert_id,
        "rack_id": rack_id,
        "rack_code": rack.get("code"),
        "rack_name": rack.get("name"),
        "building_code": rack.get("building_code"),
        "zone_code": rack.get("zone_code"),
        "occupied": occupied, "total": total, "occupancy_pct": pct,
        "severity": "critical",
        "created_at": _now(),
        "acknowledged_at": None, "acknowledged_by": None,
    }
    await db.wh_rack_alerts.insert_one(alert_doc)

    # Publish to Alert Engine (shows in notification bell, SSE-broadcast)
    try:
        from routes.rahaza_notifications import publish_notification
        title = f"Rak Kritis: {rack.get('building_code')}-{rack.get('zone_code')}-{rack.get('code')} {pct}%"
        message = (
            f"Rak {rack.get('name','')} kini terisi {occupied}/{total} slot ({pct}%). "
            f"Segera kosongkan atau redistribusi stok."
        )
        await publish_notification(
            db,
            type_="wh_rack_critical",
            severity="warning" if pct < 100 else "error",
            title=title,
            message=message,
            link_module="wh-scan",
            link_id=rack_id,
            target_roles=["warehouse_manager", "supervisor", "owner", "admin", "superadmin"],
            dedup_key=f"wh_rack_critical:{rack_id}",
        )
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"publish_notification failed for rack alert: {e}")

    return {"alert": alert_doc, "created": True}


# ─── Models ───────────────────────────────────────────────────────────────────

class PendingCreateIn(BaseModel):
    type: str = Field(..., description="inbound | outbound_rm | outbound_fg")
    source_type: str = Field("manual", description="production | shipment | purchase_order | material_issue | manual")
    source_id: Optional[str] = None
    source_ref: Optional[str] = None
    material_id: str
    material_code: str
    material_name: str
    material_type: str = Field("rm", description="rm | fg | wip")
    expected_qty: float = Field(..., gt=0)
    unit: str
    building_id: Optional[str] = None
    notes: Optional[str] = None


class ScanInIn(BaseModel):
    scanned_qty: float = Field(..., gt=0, description="Qty yang sebenarnya diterima (bisa berbeda dari expected)")
    position_barcode: Optional[str] = Field(None, description="Barcode posisi rak tujuan (scan position label)")
    lot_number: Optional[str] = None
    notes: Optional[str] = None
    # 2026-08-05 — satuan hitung fisik operator (opsional). Bila kosong, dipakai
    # satuan pada dokumen movement seperti perilaku sebelumnya.
    input_uom: Optional[str] = Field(None, description="Satuan qty yang di-scan (mis. 'box'); default satuan movement")


class ScanOutIn(BaseModel):
    scanned_qty: float = Field(..., gt=0, description="Qty yang keluar")
    position_barcode: Optional[str] = Field(None, description="Barcode posisi asal (opsional)")
    notes: Optional[str] = None


class ProductionPendingIn(BaseModel):
    """Called by production portal when WO is completed."""
    wo_id: str
    wo_number: str
    material_id: str
    material_code: str
    material_name: str
    qty_completed: float = Field(ge=0)
    unit: str
    building_id: Optional[str] = None


class ShipmentPendingIn(BaseModel):
    """Called by shipment portal when shipment is dispatched."""
    shipment_id: str
    shipment_number: str
    items: List[dict]  # [{material_id, material_code, material_name, qty, unit}]
    building_id: Optional[str] = None


class MaterialIssuePendingIn(BaseModel):
    """Called when material issue is created — requires scan-out before stock reduces."""
    issue_id: str
    issue_ref: str
    material_id: str
    material_code: str
    material_name: str
    qty: float = Field(ge=0)
    unit: str
    wo_id: Optional[str] = None
    wo_number: Optional[str] = None
    building_id: Optional[str] = None


# ══════════════════════════════════════════════════════════════════════════════
# SUMMARY
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/pending/summary")
async def pending_summary(request: Request, building_id: Optional[str] = None):
    """Quick counts for dashboard badges."""
    await require_auth(request)
    db = get_db()
    q_base = {"status": {"$in": ["pending", "partial"]}}
    if building_id:
        q_base["building_id"] = building_id

    pending_in = await db.wh_pending_movements.count_documents({**q_base, "type": "inbound"})
    pending_out_rm = await db.wh_pending_movements.count_documents({**q_base, "type": "outbound_rm"})
    pending_out_fg = await db.wh_pending_movements.count_documents({**q_base, "type": "outbound_fg"})

    return {
        "pending_inbound": pending_in,
        "pending_outbound_rm": pending_out_rm,
        "pending_outbound_fg": pending_out_fg,
        "total_pending": pending_in + pending_out_rm + pending_out_fg,
    }


# ══════════════════════════════════════════════════════════════════════════════
# LIST + CREATE
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/pending")
async def list_pending(
    request: Request,
    type: Optional[str] = None,
    status: Optional[str] = None,
    source_type: Optional[str] = None,
    building_id: Optional[str] = None,
    limit: int = Query(100, le=500),
):
    await require_auth(request)
    db = get_db()
    q = {}
    if type:
        q["type"] = type
    if status:
        q["status"] = status
    if source_type:
        q["source_type"] = source_type
    if building_id:
        q["building_id"] = building_id
    items = await db.wh_pending_movements.find(q, {"_id": 0}).sort("created_at", -1).limit(limit).to_list(500)
    return serialize_doc(items)


@router.post("/pending")
async def create_pending(data: PendingCreateIn, request: Request):
    """Manually create a pending movement (admin use)."""
    user = await require_auth(request)
    db = get_db()
    prefix = _counter_prefix(data.type)
    ref = await _next_ref(db, prefix)
    doc = {
        "id": _uid(), "ref_number": ref,
        "type": data.type, "source_type": data.source_type,
        "source_id": data.source_id or "", "source_ref": data.source_ref or "",
        "material_id": data.material_id, "material_code": data.material_code,
        "material_name": data.material_name, "material_type": data.material_type,
        "expected_qty": data.expected_qty, "scanned_qty": 0, "unit": data.unit,
        "building_id": data.building_id or "",
        "position_id": None, "position_barcode": None,
        "status": "pending", "notes": data.notes or "",
        "created_at": _now(), "created_by": user.get("email", "system"),
        "confirmed_at": None, "confirmed_by": None,
    }
    await db.wh_pending_movements.insert_one(doc)
    await log_activity(user["id"], user.get("name",""), "create", "wh_pending", f"{ref}: {data.material_name} {data.expected_qty}{data.unit} ({data.type})")
    return serialize_doc({"message": "Pending movement dibuat", "movement": doc})


# ══════════════════════════════════════════════════════════════════════════════
# SCAN-IN (INBOUND)
# ══════════════════════════════════════════════════════════════════════════════

@router.post("/pending/{movement_id}/scan-in")
async def scan_in(movement_id: str, data: ScanInIn, request: Request):
    """
    Confirm inbound: scan item received → add to stock.
    Updates wh_pending_movements status → confirmed.
    Adds to rahaza_material_stock (FG or RM depending on material_type).
    Updates wh_positions if position_barcode provided.
    """
    user = await require_auth(request)
    db = get_db()

    movement = await db.wh_pending_movements.find_one({"id": movement_id}, {"_id": 0})
    if not movement:
        raise HTTPException(404, "Pending movement tidak ditemukan")
    if movement["type"] != "inbound":
        raise HTTPException(400, f"Movement ini bukan inbound (type={movement['type']})")
    if movement["status"] == "confirmed":
        raise HTTPException(400, "Movement ini sudah dikonfirmasi")
    if movement["status"] == "cancelled":
        raise HTTPException(400, "Movement ini sudah dibatalkan")

    material_id = movement["material_id"]
    qty = data.scanned_qty
    unit = movement["unit"]
    _uom_applied = None   # jejak konversi satuan (dikembalikan ke UI bila terjadi)

    # ── 2026-08-05 · SATUAN HITUNG OPERATOR (opsional) ────────────────────────
    # Dokumen movement punya satuannya sendiri (`unit`, mis. "pcs"). Barang bisa
    # datang & dihitung dalam satuan lain (mis. per "box"/"rol"/"gram"). Bila
    # operator memilih satuan itu di layar, qty diterjemahkan DULU ke satuan
    # dokumen supaya perbandingan dengan `expected_qty`, progres, dan qty rak
    # tetap satu bahasa. Konversi ke satuan DASAR tetap dikerjakan stock_service.
    _doc_uom = _uom.normalize_code(unit)
    _op_uom = _uom.normalize_code(data.input_uom or "")
    if _op_uom and _op_uom != _doc_uom:
        _mat0 = await db.rahaza_materials.find_one({"id": material_id}, {"_id": 0})
        if not _mat0:
            raise HTTPException(400, "Master material tidak ditemukan — satuan tidak bisa dikonversi.")
        f_op, base_u, st_op, note_op = _bom_uom.line_factor(_mat0, _op_uom)
        if st_op not in ("base", "uom", "global", "fabric"):
            raise HTTPException(400, note_op or (
                f"Satuan '{_op_uom}' tidak bisa dikonversi untuk {_mat0.get('code') or 'material ini'}."))
        f_doc, _b2, st_doc, _n2 = _bom_uom.line_factor(_mat0, _doc_uom)
        if st_doc not in ("base", "uom", "global", "fabric") or not f_doc:
            f_doc = 1.0
        qty = round(float(data.scanned_qty) * float(f_op) / float(f_doc), 4)
        if qty <= 0:
            raise HTTPException(400, "Hasil konversi qty harus > 0")
        _uom_applied = {
            "input_qty": data.scanned_qty, "input_uom": _op_uom,
            "qty_doc": qty, "doc_unit": _doc_uom,
            "qty_base": round(float(data.scanned_qty) * float(f_op), 4),
            "base_unit": base_u, "factor": float(f_op), "source": st_op,
        }

    # 1. Add to material stock
    default_loc = await db.rahaza_locations.find_one({"active": True}, {"_id": 0})
    loc_id = default_loc["id"] if default_loc else None

    if loc_id and qty > 0:
        # SSOT: semua penambahan stok lewat stock_service (jaga qty+alias+available).
        # INV-1: set ownership & inventory_category agar FG produksi internal TERLIHAT
        #        oleh fulfillment (yang query ownership=cv_da, inventory_category=fg_internal).
        mat = await db.rahaza_materials.find_one({"id": material_id}, {"_id": 0})
        mtype = ((mat or {}).get("type") or movement.get("material_type") or "").lower()
        is_fg = mtype == "fg" or (movement.get("material_type") == "fg")
        meta = {
            "material_type": mtype or ("fg" if is_fg else None),
            "material_code": movement.get("material_code"),
            "material_name": movement.get("material_name"),
            "ownership": "cv_da",
            "inventory_category": "fg_internal" if is_fg else "raw_material",
            "unit": unit,
        }
        # `unit` pada movement boleh berupa satuan kemasan (mis. "bks").
        # stock_service mengonversinya ke satuan dasar bila dikenal; bila sama
        # dengan satuan dasar atau tidak dikenal, perilakunya tidak berubah.
        _in_uom = None
        try:
            if mat and unit and _uom.normalize_code(unit) != _uom.base_uom_of(mat) \
                    and _uom.find_uom(mat, unit):
                _in_uom = _uom.normalize_code(unit)
        except Exception:  # noqa: BLE001 — konversi bersifat opsional
            _in_uom = None
        await stock_service.add(
            material_id, loc_id, qty, meta=meta,
            ref={"source": "wh_scan_in", "movement_id": movement_id,
                 "ref_number": movement.get("ref_number"),
                 "source_type": movement.get("source_type"),
                 "source_id": movement.get("source_id")},
            actor={"id": user.get("id"), "email": user.get("email")},
            db=db, input_uom=_in_uom,
        )

    # 2. Log FG movement
    await db.rahaza_fg_movements.insert_one({
        "id": _uid(), "material_id": material_id,
        "fg_code": movement.get("material_code"),
        "direction": "in", "qty": qty, "unit": unit,
        "source": "wh_scan_in",
        "movement_id": movement_id, "ref_number": movement.get("ref_number"),
        "source_type": movement.get("source_type"), "source_id": movement.get("source_id"),
        "notes": data.notes or "", "lot_number": data.lot_number,
        "timestamp": _now(), "created_by": user.get("email", "system"),
    })

    # 3. Update position if provided
    position_id = None
    if data.position_barcode:
        pos = await db.wh_positions.find_one({"barcode": data.position_barcode}, {"_id": 0})
        if pos:
            position_id = pos["id"]
            new_qty = pos.get("qty", 0) + qty
            await db.wh_positions.update_one(
                {"id": pos["id"]},
                {"$set": {
                    "material_id": material_id,
                    "material_code": movement.get("material_code"),
                    "material_name": movement.get("material_name"),
                    "qty": new_qty, "unit": unit,
                    "status": "occupied", "last_updated": _now(),
                    "lot_number": data.lot_number,
                }}
            )
            # Trigger rack occupancy alert check (non-blocking, best-effort)
            try:
                await helper_check_rack_occupancy_alert(db, pos.get("rack_id"))
            except Exception:
                logging.getLogger(__name__).debug("suppressed exception", exc_info=True)

    # 4. Update movement
    new_scanned = movement.get("scanned_qty", 0) + qty
    new_status = "confirmed" if new_scanned >= movement["expected_qty"] else "partial"
    await db.wh_pending_movements.update_one(
        {"id": movement_id},
        {"$set": {
            "scanned_qty": new_scanned, "status": new_status,
            "position_id": position_id,
            "position_barcode": data.position_barcode,
            "confirmed_at": _now() if new_status == "confirmed" else None,
            "confirmed_by": user.get("email") if new_status == "confirmed" else None,
            "lot_number": data.lot_number,
        }}
    )

    await log_activity(user["id"], user.get("name",""), "scan_in", "wh_receiving",
        f"Scan-in {movement.get('ref_number')}: {movement.get('material_name')} {qty}{unit} → {new_status}")

    return serialize_doc({
        "ok": True,
        "ref_number": movement.get("ref_number"),
        "material_name": movement.get("material_name"),
        "scanned_qty": qty,
        "total_scanned": new_scanned,
        "expected_qty": movement["expected_qty"],
        "status": new_status,
        "position_barcode": data.position_barcode,
        # transparansi konversi satuan (2026-08-05) — UI menampilkan "3 box = 36 pcs"
        "uom_applied": _uom_applied,
    })


# ══════════════════════════════════════════════════════════════════════════════
# SCAN-OUT (OUTBOUND)
# ══════════════════════════════════════════════════════════════════════════════

@router.post("/pending/{movement_id}/scan-out")
async def scan_out(movement_id: str, data: ScanOutIn, request: Request):
    """
    Confirm outbound: scan item being issued → reduce stock.
    Works for both outbound_rm (raw material) and outbound_fg (finished goods).
    """
    user = await require_auth(request)
    db = get_db()

    movement = await db.wh_pending_movements.find_one({"id": movement_id}, {"_id": 0})
    if not movement:
        raise HTTPException(404, "Pending movement tidak ditemukan")
    if movement["type"] not in ("outbound_rm", "outbound_fg"):
        raise HTTPException(400, f"Movement ini bukan outbound (type={movement['type']})")
    if movement["status"] == "confirmed":
        raise HTTPException(400, "Movement ini sudah dikonfirmasi")
    if movement["status"] == "cancelled":
        raise HTTPException(400, "Movement ini sudah dibatalkan")

    material_id = movement["material_id"]
    qty = data.scanned_qty
    unit = movement["unit"]

    # 1+2. Reduce stock via stock_service (jaga qty+alias+available konsisten).
    #    Fulfillment FG (dispatch buyer): kurangi BARIS spesifik by stock_id + lepas reserved.
    #    Lainnya (maklon RM, SJ internal, CMT): kurangi by (material_id, lokasi default).
    is_fulfillment_fg = (
        movement.get("type") == "outbound_fg"
        and movement.get("source_type") == "fulfillment"
        and movement.get("stock_id")
    )
    _ref = {"source": f"wh_scan_out_{movement['type']}", "movement_id": movement_id,
            "ref_number": movement.get("ref_number"), "source_type": movement.get("source_type"),
            "source_id": movement.get("source_id")}
    _actor = {"id": user.get("id"), "email": user.get("email")}
    stock_remaining = None
    try:
        if is_fulfillment_fg:
            _srow = await stock_service.issue_row(movement["stock_id"], qty, release_reserved=True,
                                                  ref=_ref, actor=_actor, db=db)
            stock_remaining = read_qty(_srow)
        else:
            default_loc = await db.rahaza_locations.find_one({"active": True}, {"_id": 0})
            loc_id = default_loc["id"] if default_loc else None
            if loc_id:
                _srow = await stock_service.issue(material_id, loc_id, qty, ref=_ref, actor=_actor, db=db)
                stock_remaining = read_qty(_srow)
    except stock_service.InsufficientStock as e:
        raise HTTPException(400, f"Stok tidak cukup: tersedia {e.available:.2f}{unit}, diminta {qty:.2f}{unit}")

    # 3. Log movement
    direction_label = "outbound_rm" if movement["type"] == "outbound_rm" else "outbound_fg"
    await db.rahaza_fg_movements.insert_one({
        "id": _uid(), "material_id": material_id,
        "fg_code": movement.get("material_code"),
        "direction": "out", "qty": qty, "unit": unit,
        "source": f"wh_scan_out_{direction_label}",
        "movement_id": movement_id, "ref_number": movement.get("ref_number"),
        "source_type": movement.get("source_type"), "source_id": movement.get("source_id"),
        "notes": data.notes or "",
        "timestamp": _now(), "created_by": user.get("email", "system"),
    })

    # 4. Update position if provided
    if data.position_barcode:
        pos = await db.wh_positions.find_one({"barcode": data.position_barcode}, {"_id": 0})
        if pos:
            new_qty = max(0, pos.get("qty", 0) - qty)
            await db.wh_positions.update_one(
                {"id": pos["id"]},
                {"$set": {
                    "qty": new_qty,
                    "status": "empty" if new_qty == 0 else "occupied",
                    "last_updated": _now(),
                    "material_id": None if new_qty == 0 else pos.get("material_id"),
                    "material_code": None if new_qty == 0 else pos.get("material_code"),
                    "material_name": None if new_qty == 0 else pos.get("material_name"),
                }}
            )

    # 5. Update movement
    new_scanned = movement.get("scanned_qty", 0) + qty
    new_status = "confirmed" if new_scanned >= movement["expected_qty"] else "partial"
    await db.wh_pending_movements.update_one(
        {"id": movement_id},
        {"$set": {
            "scanned_qty": new_scanned, "status": new_status,
            "confirmed_at": _now() if new_status == "confirmed" else None,
            "confirmed_by": user.get("email") if new_status == "confirmed" else None,
        }}
    )

    # 6. Source-specific finalization (best-effort, non-blocking).
    #    Dispatch buyer: setelah SEMUA outbound_fg untuk order ter-scan-out penuh,
    #    posting COGS + tandai order 'dispatched'.
    finalize = None
    if new_status == "confirmed" and movement.get("source_type") == "fulfillment" and movement.get("source_id"):
        try:
            from routes.fulfillment import finalize_fulfillment_dispatch
            finalize = await finalize_fulfillment_dispatch(db, movement["source_id"], user)
        except Exception as e:
            logging.getLogger(__name__).warning(f"finalize_fulfillment_dispatch gagal: {e}")

    await log_activity(user["id"], user.get("name",""), "scan_out", "wh_receiving",
        f"Scan-out {movement.get('ref_number')}: {movement.get('material_name')} -{qty}{unit} → {new_status}")

    return serialize_doc({
        "ok": True,
        "ref_number": movement.get("ref_number"),
        "material_name": movement.get("material_name"),
        "scanned_qty": qty,
        "total_scanned": new_scanned,
        "expected_qty": movement["expected_qty"],
        "status": new_status,
        "stock_remaining": stock_remaining,
        "finalize": finalize,
    })


@router.post("/pending/{movement_id}/cancel")
async def cancel_pending(movement_id: str, request: Request):
    user = await require_auth(request)
    db = get_db()
    movement = await db.wh_pending_movements.find_one({"id": movement_id}, {"_id": 0})
    if not movement:
        raise HTTPException(404, "Pending movement tidak ditemukan")
    if movement["status"] == "confirmed":
        raise HTTPException(400, "Movement yang sudah dikonfirmasi tidak bisa dibatalkan")
    await db.wh_pending_movements.update_one(
        {"id": movement_id},
        {"$set": {"status": "cancelled", "cancelled_at": _now(), "cancelled_by": user.get("email")}}
    )
    return {"message": "Movement dibatalkan"}


# ══════════════════════════════════════════════════════════════════════════════
# AUTO-CREATE FROM OTHER PORTALS
# ══════════════════════════════════════════════════════════════════════════════

@router.post("/pending/create-from-production")
async def create_from_production(data: ProductionPendingIn, request: Request):
    """
    Called internally when a Work Order is completed.
    Creates a PENDING INBOUND for FG — stok NOT yet added.
    """
    await require_auth(request)
    db = get_db()

    # Don't create duplicate for same WO
    existing = await db.wh_pending_movements.find_one({
        "source_id": data.wo_id, "source_type": "production",
        "status": {"$in": ["pending", "partial"]},
    })
    if existing:
        return serialize_doc({"message": "Pending inbound sudah ada", "existing_id": existing["id"]})

    ref = await _next_ref(db, "RCV")
    doc = {
        "id": _uid(), "ref_number": ref,
        "type": "inbound", "source_type": "production",
        "source_id": data.wo_id, "source_ref": data.wo_number,
        "material_id": data.material_id, "material_code": data.material_code,
        "material_name": data.material_name, "material_type": "fg",
        "expected_qty": data.qty_completed, "scanned_qty": 0,
        "unit": data.unit,
        "building_id": data.building_id or "",
        "position_id": None, "position_barcode": None,
        "status": "pending",
        "notes": f"Dari WO: {data.wo_number}",
        "created_at": _now(), "created_by": "production_portal",
        "confirmed_at": None, "confirmed_by": None,
    }
    await db.wh_pending_movements.insert_one(doc)
    return serialize_doc({"message": f"Pending inbound {ref} dibuat untuk WO {data.wo_number}", "id": doc["id"]})


@router.post("/pending/create-from-shipment")
async def create_from_shipment(data: ShipmentPendingIn, request: Request):
    """
    Called when a shipment is dispatched.
    Creates PENDING OUTBOUND_FG for each line item.
    """
    await require_auth(request)
    db = get_db()
    created = []
    for item in data.items:
        ref = await _next_ref(db, "IFG")
        doc = {
            "id": _uid(), "ref_number": ref,
            "type": "outbound_fg", "source_type": "shipment",
            "source_id": data.shipment_id, "source_ref": data.shipment_number,
            "material_id": item.get("material_id", ""), "material_code": item.get("material_code", ""),
            "material_name": item.get("material_name", ""), "material_type": "fg",
            "expected_qty": item.get("qty", 0), "scanned_qty": 0,
            "unit": item.get("unit", "pcs"),
            "building_id": data.building_id or "",
            "position_id": None, "position_barcode": None,
            "status": "pending",
            "notes": f"Shipment: {data.shipment_number}",
            "created_at": _now(), "created_by": "shipment_portal",
            "confirmed_at": None, "confirmed_by": None,
        }
        await db.wh_pending_movements.insert_one(doc)
        created.append({"id": doc["id"], "ref_number": ref})
    return serialize_doc({"message": f"{len(created)} pending outbound dibuat", "created": created})


@router.post("/pending/create-from-material-issue")
async def create_from_material_issue(data: MaterialIssuePendingIn, request: Request):
    """
    Called when material issue is requested.
    Creates PENDING OUTBOUND_RM — MUST scan-out before stock reduces.
    """
    user = await require_auth(request)
    db = get_db()

    existing = await db.wh_pending_movements.find_one({
        "source_id": data.issue_id, "source_type": "material_issue",
        "status": {"$in": ["pending", "partial"]},
    })
    if existing:
        return serialize_doc({"ok": True, "pending_id": existing["id"], "message": "Pending sudah ada"})

    ref = await _next_ref(db, "IRM")
    doc = {
        "id": _uid(), "ref_number": ref,
        "type": "outbound_rm", "source_type": "material_issue",
        "source_id": data.issue_id, "source_ref": data.issue_ref,
        "material_id": data.material_id, "material_code": data.material_code,
        "material_name": data.material_name, "material_type": "rm",
        "expected_qty": data.qty, "scanned_qty": 0,
        "unit": data.unit,
        "building_id": data.building_id or "",
        "position_id": None, "position_barcode": None,
        "status": "pending",
        "notes": f"WO: {data.wo_number or '-'}",
        "created_at": _now(), "created_by": user.get("email", "system"),
        "confirmed_at": None, "confirmed_by": None,
    }
    await db.wh_pending_movements.insert_one(doc)
    return serialize_doc({"ok": True, "pending_id": doc["id"], "ref_number": ref,
                           "message": f"Pending outbound RM {ref} dibuat. Scan-out diperlukan sebelum stok berkurang."})



# ══════════════════════════════════════════════════════════════════════════════
# STOCK RESET — bersihkan semua stok, semua mutasi baru harus lewat scan-in
# ══════════════════════════════════════════════════════════════════════════════

@router.post("/stock/reset-all")
async def reset_all_stock(request: Request):
    """
    DANGEROUS: Reset semua stok ke 0 supaya seluruh pergerakan stok ke depan
    WAJIB melewati WMS Scan-In / Scan-Out.
    - rahaza_material_stock → qty = 0
    - wh_positions → qty = 0, status = empty, clear material
    - wh_pending_movements (pending/partial) → status = cancelled
    """
    user = await require_auth(request)
    db = get_db()

    # GUARD: reset-all sangat destruktif → hanya admin/owner atau permission khusus.
    role = (user.get("role") or "").lower()
    perms = user.get("_permissions") or []
    if role not in ("superadmin", "admin", "owner") and not (
        "*" in perms or "inventory.manage" in perms or "warehouse.manage" in perms
    ):
        raise HTTPException(403, "Forbidden: reset stok hanya untuk admin/owner (butuh permission inventory/warehouse).")

    # Zero-out LENGKAP: qty + semua alias + available + reserved (hindari sisa Schema C 'terlihat ada').
    reset_fields = {**set_all_qty(0), "available_quantity": 0.0, "reserved_quantity": 0.0, "reserved": 0.0, "updated_at": _now()}
    r1 = await db.rahaza_material_stock.update_many({}, {"$set": reset_fields})
    r2 = await db.wh_positions.update_many(
        {},
        {"$set": {
            "qty": 0, "status": "empty",
            "material_id": None, "material_code": None, "material_name": None,
            "lot_number": None, "last_updated": _now(),
        }}
    )
    r3 = await db.wh_pending_movements.update_many(
        {"status": {"$in": ["pending", "partial"]}},
        {"$set": {"status": "cancelled", "cancelled_at": _now(), "cancelled_by": user.get("email", "system")}}
    )
    # Log reset event
    await db.rahaza_fg_movements.insert_one({
        "id": _uid(), "direction": "reset",
        "source": "wms_stock_reset",
        "notes": "Stock reset-all triggered — semua qty dibersihkan",
        "timestamp": _now(), "created_by": user.get("email", "system"),
    })
    await log_activity(user["id"], user.get("name", ""), "reset", "wms_stock", "Reset all stock to 0")

    return {
        "message": "Semua stok telah direset ke 0. Gunakan Scan-In untuk memasukkan stok awal.",
        "material_stock_rows_reset": r1.modified_count,
        "positions_reset": r2.modified_count,
        "pending_cancelled": r3.modified_count,
    }


@router.get("/stock/status")
async def stock_status(request: Request):
    """Quick sanity: how much stock currently recorded."""
    await require_auth(request)
    db = get_db()
    agg = await db.rahaza_material_stock.aggregate([
        {"$group": {"_id": None, "total_rows": {"$sum": 1}, "total_qty": {"$sum": "$qty"}}}
    ]).to_list(1)
    summary = agg[0] if agg else {"total_rows": 0, "total_qty": 0}
    occupied = await db.wh_positions.count_documents({"status": "occupied"})
    total_pos = await db.wh_positions.count_documents({})
    return {
        "material_stock_rows": summary["total_rows"],
        "material_stock_total_qty": summary["total_qty"],
        "positions_occupied": occupied,
        "positions_total": total_pos,
    }



# ══════════════════════════════════════════════════════════════════════════════
# RACK OCCUPANCY ALERTS — list + acknowledge + manual re-scan
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/rack-alerts")
async def list_rack_alerts(request: Request, active_only: bool = True, limit: int = 100):
    """List rack critical alerts. Default hanya yang belum di-ack & masih aktif (<24h)."""
    await require_auth(request)
    db = get_db()
    from datetime import timedelta
    q = {}
    if active_only:
        q["acknowledged_at"] = None
        cutoff = _now() - timedelta(hours=24)
        q["created_at"] = {"$gte": cutoff}
    rows = await db.wh_rack_alerts.find(q, {"_id": 0}).sort("created_at", -1).limit(limit).to_list(500)
    return serialize_doc(rows)


@router.post("/rack-alerts/{alert_id}/acknowledge")
async def ack_rack_alert(alert_id: str, request: Request):
    """Tandai alert sebagai sudah ditangani."""
    user = await require_auth(request)
    db = get_db()
    res = await db.wh_rack_alerts.update_one(
        {"id": alert_id, "acknowledged_at": None},
        {"$set": {"acknowledged_at": _now(), "acknowledged_by": user.get("email") or user.get("name", "")}}
    )
    if res.matched_count == 0:
        raise HTTPException(404, "Alert tidak ditemukan atau sudah di-ack")
    return {"message": "Alert ditandai sudah ditangani"}


@router.post("/rack-alerts/scan-all")
async def scan_all_racks(request: Request):
    """Manual re-scan semua rak — buat alert untuk rak ≥95% yang belum ada alert aktif."""
    await require_auth(request)
    db = get_db()
    racks = await db.wh_racks.find({"active": True}, {"_id": 0, "id": 1}).to_list(500)
    created = 0
    existing = 0
    for r in racks:
        result = await helper_check_rack_occupancy_alert(db, r["id"])
        if not result:
            continue
        if result.get("created"):
            created += 1
        else:
            existing += 1
    return {
        "message": f"Scan selesai. {created} alert baru dibuat, {existing} alert sudah ada.",
        "new_alerts": created,
        "existing_alerts": existing,
    }
