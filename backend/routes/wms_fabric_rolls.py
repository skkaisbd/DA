"""
WMS — Fabric Roll Tracking (P0-WH-1)
CV. Dewi Aditya — Garment-grade kain/roll tracking

Collections:
  wh_fabric_rolls:
    id, roll_no (unique), material_id, material_code, material_name,
    color, color_lot, supplier_name, uom (meter|kg),
    length_m, weight_kg, received_date, po_no,
    qc_status (pending|pass|partial|reject),
    status (in_stock|partly_issued|fully_issued|returned|rejected),
    position_id, position_barcode,
    remaining_m, remaining_kg,
    unit_cost, notes,
    created_at, created_by, updated_at, updated_by

  wh_fabric_roll_movements:
    id, roll_id, roll_no, movement_type (receive|putaway|issue|return|adjust|reject),
    qty, unit, reference_type (po|wo|cmt|manual), reference_id, reference_no,
    from_location, to_location, notes,
    created_at, created_by

Endpoints (prefix /api/wms/fabric-rolls):
  GET    /                          list + filters (material, color, status, qc, position)
  POST   /                          create new roll (from receiving)
  GET    /{roll_id}                  detail + movements
  PUT    /{roll_id}                  update (qc_status, position, notes)
  DELETE /{roll_id}                  soft delete (only draft/pending)
  POST   /{roll_id}/putaway          assign to position
  POST   /{roll_id}/issue            issue to WO/CMT (reduce remaining)
  POST   /{roll_id}/return           return remaining to stock
  POST   /{roll_id}/reject           mark as reject + supplier claim
  POST   /{roll_id}/adjust           manual quantity adjust
  GET    /stats/summary              aggregate: total rolls, meters, kg by status
  GET    /by-material/{material_id}  all rolls for a material
  GET    /by-lot/{color_lot}         all rolls in same lot
  GET    /{roll_id}/label-pdf        barcode label PDF
"""
# ruff: noqa: F401
import uuid
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, HTTPException, Request, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from database import get_db
from auth import require_auth, serialize_doc
from core import fabric_roll_engine  # FASE H-5: satu pintu penerbitan & pemakaian roll
import io
import logging

try:
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from barcode import Code128
    from barcode.writer import ImageWriter
    from PIL import Image as PILImage
    REPORTLAB_OK = True
except ImportError:
    REPORTLAB_OK = False

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/wms/fabric-rolls", tags=["wms-fabric-rolls"])

QC_STATUSES = ["pending", "pass", "partial", "reject"]
ROLL_STATUSES = ["in_stock", "partly_issued", "fully_issued", "returned", "rejected"]


def _now(): return datetime.now(timezone.utc)
def _id(): return str(uuid.uuid4())


class RollIn(BaseModel):
    # FASE H-5: nomor roll TIDAK diketik. Dikosongkan → diterbitkan otomatis lewat
    # SSOT penomoran (`wh_fabric_rolls.roll_no`, bawaan `RL-{YYYY}{MM}-{SEQ:4}`).
    # Kalau Administrasi Sistem mengubah mode jenis dokumen ini ke MANUAL, nomor
    # yang dikirim tetap diperiksa terhadap polanya — bukan diterima apa adanya.
    roll_no: str = Field("", description="Kosongkan — nomor roll diterbitkan otomatis")
    material_id: str
    material_code: str
    material_name: str
    color: str = ""
    color_lot: str = ""
    supplier_name: str = ""
    uom: str = Field("meter", pattern="^(meter|kg|yard)$")
    length_m: float = Field(0.0, ge=0)
    weight_kg: float = Field(0.0, ge=0)
    received_date: Optional[str] = None
    po_no: str = ""
    qc_status: str = Field("pending")
    unit_cost: float = Field(0.0, ge=0)
    notes: str = ""


class PutAwayIn(BaseModel):
    position_id: str
    position_barcode: str = ""
    notes: str = ""


class IssueIn(BaseModel):
    qty: float = Field(..., gt=0, description="Quantity dalam UOM (meter atau kg)")
    unit: str = "meter"
    reference_type: str = Field("wo", pattern="^(wo|cmt|manual)$")
    reference_id: str = ""
    reference_no: str = ""
    notes: str = ""


class ReturnIn(BaseModel):
    qty: float = Field(..., gt=0)
    unit: str = "meter"
    reference_type: str = "wo"
    reference_id: str = ""
    reference_no: str = ""
    notes: str = ""


class RejectIn(BaseModel):
    reason: str = Field(..., min_length=3)
    claim_to_supplier: bool = False
    notes: str = ""


class AdjustIn(BaseModel):
    delta_m: float = Field(0.0, description="+/- meter adjustment")
    delta_kg: float = Field(0.0, description="+/- kg adjustment")
    reason: str = Field(..., min_length=3)


# ── Helpers ─────────────────────────────────────────────────────────────────────

async def _log_movement(db, roll: dict, movement_type: str, qty: float, unit: str,
                        ref_type: str, ref_id: str, ref_no: str,
                        from_loc: str, to_loc: str, notes: str, user_name: str):
    mov = {
        "id": _id(),
        "roll_id": roll["id"],
        "roll_no": roll["roll_no"],
        "movement_type": movement_type,
        "qty": qty,
        "unit": unit,
        "reference_type": ref_type,
        "reference_id": ref_id,
        "reference_no": ref_no,
        "from_location": from_loc,
        "to_location": to_loc,
        "notes": notes,
        "created_at": _now(),
        "created_by": user_name,
    }
    await db.wh_fabric_roll_movements.insert_one(mov)


def _recalc_status(roll: dict) -> str:
    remaining = roll.get("remaining_m", 0) or roll.get("remaining_kg", 0)
    if roll.get("status") in ("rejected", "returned"):
        return roll["status"]
    original = roll.get("length_m", 0) or roll.get("weight_kg", 0)
    if original <= 0:
        return "in_stock"
    if remaining <= 0:
        return "fully_issued"
    if remaining < original:
        return "partly_issued"
    return "in_stock"


# ── Endpoints ─────────────────────────────────────────────────────────────────────

@router.get("")
async def list_rolls(
    request: Request,
    material_id: Optional[str] = None,
    material_code: Optional[str] = None,
    color: Optional[str] = None,
    color_lot: Optional[str] = None,
    status: Optional[str] = None,
    qc_status: Optional[str] = None,
    position_id: Optional[str] = None,
    search: Optional[str] = None,
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
):
    await require_auth(request)
    db = get_db()
    q = {}
    if material_id:
        q["material_id"] = material_id
    if material_code:
        q["material_code"] = {"$regex": material_code, "$options": "i"}
    if color:
        q["color"] = {"$regex": color, "$options": "i"}
    if color_lot:
        q["color_lot"] = {"$regex": color_lot, "$options": "i"}
    if status:
        q["status"] = status
    if qc_status:
        q["qc_status"] = qc_status
    if position_id:
        q["position_id"] = position_id
    if search:
        q["$or"] = [
            {"roll_no": {"$regex": search, "$options": "i"}},
            {"material_name": {"$regex": search, "$options": "i"}},
            {"color": {"$regex": search, "$options": "i"}},
            {"color_lot": {"$regex": search, "$options": "i"}},
            {"supplier_name": {"$regex": search, "$options": "i"}},
        ]
    total = await db.wh_fabric_rolls.count_documents(q)
    skip = (page - 1) * limit
    rolls = await db.wh_fabric_rolls.find(q, {"_id": 0}).sort("received_date", -1).skip(skip).limit(limit).to_list(limit)
    return {
        # Setiap roll dikirim BESERTA satuan aslinya (`uom`, `qty_total`,
        # `qty_remaining`) + info konversi `qty_*_m`. Layar tidak boleh lagi
        # menebak "meter" dari nama field `length_m`/`remaining_m` (2026-08-21).
        "items": [serialize_doc(fabric_roll_engine.with_display_uom(r)) for r in rolls],
        "pagination": {
            "page": page, "limit": limit, "total": total,
            "total_pages": max(1, (total + limit - 1) // limit),
            "has_next": (skip + limit) < total,
            "has_prev": page > 1,
        }
    }


@router.post("")
async def create_roll(data: RollIn, request: Request):
    user = await require_auth(request)
    db = get_db()
    # FASE H-5: nomor roll lewat SSOT penomoran. Mode `auto` (bawaan) MENOLAK nomor
    # ketikan dengan pesan yang menyebut nomor yang akan dipakai — pemakai yang
    # mengetik nomor lalu melihat nomor lain muncul akan menyimpulkan sistemnya rusak.
    roll_no = await fabric_roll_engine.issue_roll_no(db, requested=data.roll_no)
    if await db.wh_fabric_rolls.find_one({"roll_no": roll_no}):
        raise HTTPException(409, f"Roll dengan nomor '{roll_no}' sudah ada")
    qty = float(data.length_m or 0) or float(data.weight_kg or 0)
    if qty <= 0:
        raise HTTPException(400, "Isi panjang (meter/yard) atau berat (kg) roll — harus lebih dari 0.")
    roll_id = _id()
    now = _now()
    roll = {
        "id": roll_id,
        "roll_no": roll_no,
        "material_id": data.material_id,
        "material_code": data.material_code,
        "material_name": data.material_name,
        "color": data.color,
        "color_lot": data.color_lot,
        "supplier_name": data.supplier_name,
        "uom": data.uom,
        "length_m": data.length_m,
        "weight_kg": data.weight_kg,
        "remaining_m": data.length_m,
        "remaining_kg": data.weight_kg,
        "received_date": data.received_date or now.date().isoformat(),
        "po_no": data.po_no,
        "qc_status": data.qc_status,
        "status": "in_stock",
        "position_id": None,
        "position_barcode": "",
        "unit_cost": data.unit_cost,
        "notes": data.notes,
        "created_at": now,
        "created_by": user.get("name", user["id"]),
        "updated_at": now,
        "updated_by": user.get("name", user["id"]),
    }
    await db.wh_fabric_rolls.insert_one(roll)
    await _log_movement(db, roll, "receive", data.length_m or data.weight_kg,
                        data.uom, "manual", "", data.po_no, "", "gudang",
                        f"Roll {roll_no} diterima", user.get("name", ""))
    out = await db.wh_fabric_rolls.find_one({"id": roll_id}, {"_id": 0})
    return {"ok": True, "roll": serialize_doc(out)}


# ── FASE H-5: penerimaan kain yang belum punya gulungan (backfill) ───────────────
# Kenapa endpoint ini ada: kain yang sudah masuk stok tetapi tidak punya satu pun
# gulungan akan MENGHENTIKAN Portal Cutting (H-6 mewajibkan roll). Daftar ini
# membuat lubangnya kelihatan sebelum bagian potong berhenti bekerja, dan
# tombolnya menerbitkan roll untuk penerimaan yang sudah lewat.

@router.get("/number-policy")
async def roll_number_policy(request: Request):
    """Format + contoh nomor roll berikutnya (untuk petunjuk di layar)."""
    await require_auth(request)
    db = get_db()
    from core.doc_number_policy import next_preview, policy
    pol = await policy(db, fabric_roll_engine.ROLL_NUMBER_KEY)
    try:
        preview = await next_preview(db, fabric_roll_engine.ROLL_NUMBER_KEY, None)
    except Exception as e:  # noqa: BLE001 — petunjuk UI tak boleh menjatuhkan layar
        log.warning(f"roll number preview gagal: {e}")
        preview = pol.get("contoh") or ""
    return {"key": pol["key"], "label": pol["label"], "mode": pol["mode"],
            "format": pol["format"], "contoh": pol.get("contoh"), "next_number": preview}


@router.get("/missing-from-receipts")
async def missing_from_receipts(request: Request, limit: int = Query(50, ge=1, le=200)):
    """Baris penerimaan kain berstatus `received` yang belum punya gulungan."""
    await require_auth(request)
    db = get_db()
    rows = await fabric_roll_engine.receipts_missing_rolls(db, limit=limit)
    return {"items": serialize_doc(rows), "total": len(rows)}


class IssueFromReceiptIn(BaseModel):
    receipt_id: str = Field(..., min_length=1)
    item_id: str = Field(..., min_length=1)
    lines: list = Field(..., description="[{qty, color_lot, notes}] — total harus = qty diterima")


@router.post("/issue-from-receipt")
async def issue_from_receipt(data: IssueFromReceiptIn, request: Request):
    """Terbitkan gulungan untuk satu baris penerimaan yang sudah lewat (idempoten)."""
    user = await require_auth(request)
    db = get_db()
    gr = await db.warehouse_receiving.find_one({"id": data.receipt_id}, {"_id": 0})
    if not gr:
        raise HTTPException(404, "Penerimaan barang tidak ditemukan.")
    if gr.get("status") != "received":
        raise HTTPException(400, (
            f"GR {gr.get('receipt_number','')} berstatus '{gr.get('status')}'. Gulungan hanya "
            "diterbitkan untuk penerimaan yang sudah diterima — selesaikan penerimaannya dulu "
            "(rincian roll bisa diisi langsung di layar Penerimaan Barang)."))
    item = next((it for it in (gr.get("items") or []) if it.get("id") == data.item_id), None)
    if not item:
        raise HTTPException(404, "Baris penerimaan tidak ditemukan di GR tersebut.")
    already = await db.wh_fabric_rolls.count_documents({"source_receipt_item_id": data.item_id})
    if already:
        raise HTTPException(409, (
            f"Baris ini sudah punya {already} gulungan. Menerbitkan ulang akan membuat dua "
            "gulungan fisik untuk kain yang sama — dibatalkan."))
    mat = await db.rahaza_materials.find_one(
        {"id": item.get("material_id")},
        {"_id": 0, "id": 1, "code": 1, "name": 1, "unit": 1, "type": 1,
         "is_cut_panel": 1, "color": 1, "color_name": 1})
    if not mat:
        raise HTTPException(400, "Material baris penerimaan tidak ditemukan di master.")
    if not fabric_roll_engine.is_roll_material(mat):
        raise HTTPException(400, (
            f"{mat.get('code')} bersatuan '{mat.get('unit')}' tidak dilacak per gulungan."))
    accepted = float(item.get("accepted_qty") if item.get("accepted_qty") is not None
                     else max(0.0, float(item.get("received_qty", 0) or 0)
                              - float(item.get("rejected_qty", 0) or 0)))
    lines_ok = fabric_roll_engine.validate_roll_lines(
        data.lines, accepted, mat.get("unit") or "",
        f"{mat.get('code')} — {mat.get('name')}")
    made = await fabric_roll_engine.create_rolls_from_receipt(
        db, gr, item, mat, lines_ok, user)
    roll_nos = [r["roll_no"] for r in made]
    # Jejak dua arah: baris GR menyimpan gulungan yang lahir darinya.
    await db.warehouse_receiving.update_one(
        {"id": data.receipt_id, "items.id": data.item_id},
        {"$set": {
            "items.$.rolls": lines_ok,
            "items.$.roll_ids": [r["id"] for r in made],
            "items.$.roll_numbers": roll_nos,
            "updated_at": _now(),
        }},
    )
    await db.warehouse_receiving.update_one(
        {"id": data.receipt_id},
        {"$pull": {"rolls_pending": {"item_id": data.item_id}},
         "$push": {"rolls_created": {"$each": roll_nos}}},
    )
    log.info(f"H-5 backfill: {len(made)} roll terbit dari GR {gr.get('receipt_number','')} "
             f"baris {data.item_id}")
    return {"ok": True, "rolls": serialize_doc(made), "roll_numbers": roll_nos,
            "message": (f"{len(made)} gulungan diterbitkan untuk "
                        f"{mat.get('code')} — {mat.get('name')}: {', '.join(roll_nos)}")}


@router.get("/stats/summary")
async def roll_stats(request: Request):
    await require_auth(request)
    db = get_db()
    pipeline = [
        {"$group": {
            "_id": "$status",
            "count": {"$sum": 1},
            "total_m": {"$sum": "$remaining_m"},
            "total_kg": {"$sum": "$remaining_kg"},
        }}
    ]
    stats = await db.wh_fabric_rolls.aggregate(pipeline).to_list(20)
    return {"by_status": [{**s, "_id": s["_id"]} for s in stats]}


@router.get("/by-material/{material_id}")
async def rolls_by_material(material_id: str, request: Request):
    await require_auth(request)
    db = get_db()
    rolls = await db.wh_fabric_rolls.find({"material_id": material_id}, {"_id": 0}).sort("received_date", -1).to_list(500)
    return [serialize_doc(fabric_roll_engine.with_display_uom(r)) for r in rolls]


@router.get("/by-lot/{color_lot}")
async def rolls_by_lot(color_lot: str, request: Request):
    await require_auth(request)
    db = get_db()
    rolls = await db.wh_fabric_rolls.find({"color_lot": {"$regex": color_lot, "$options": "i"}}, {"_id": 0}).to_list(500)
    return [serialize_doc(r) for r in rolls]


@router.get("/{roll_id}")
async def get_roll(roll_id: str, request: Request):
    await require_auth(request)
    db = get_db()
    roll = await db.wh_fabric_rolls.find_one({"$or": [{"id": roll_id}, {"roll_no": roll_id}]}, {"_id": 0})
    if not roll:
        raise HTTPException(404, "Roll tidak ditemukan")
    movements = await db.wh_fabric_roll_movements.find({"roll_id": roll["id"]}, {"_id": 0}).sort("created_at", -1).to_list(100)
    return {**serialize_doc(fabric_roll_engine.with_display_uom(roll)),
            "movements": [serialize_doc(m) for m in movements]}


@router.put("/{roll_id}")
async def update_roll(roll_id: str, data: dict, request: Request):
    user = await require_auth(request)
    db = get_db()
    roll = await db.wh_fabric_rolls.find_one({"id": roll_id})
    if not roll:
        raise HTTPException(404, "Roll tidak ditemukan")
    allowed = {"qc_status", "notes", "color", "color_lot", "supplier_name", "unit_cost", "po_no"}
    updates = {k: v for k, v in data.items() if k in allowed}
    if not updates:
        raise HTTPException(400, "Tidak ada field yang dapat diupdate")
    updates["updated_at"] = _now()
    updates["updated_by"] = user.get("name", user["id"])
    await db.wh_fabric_rolls.update_one({"id": roll_id}, {"$set": updates})
    out = await db.wh_fabric_rolls.find_one({"id": roll_id}, {"_id": 0})
    return {"ok": True, "roll": serialize_doc(out)}


@router.post("/{roll_id}/putaway")
async def putaway_roll(roll_id: str, data: PutAwayIn, request: Request):
    user = await require_auth(request)
    db = get_db()
    roll = await db.wh_fabric_rolls.find_one({"id": roll_id})
    if not roll:
        raise HTTPException(404, "Roll tidak ditemukan")
    if roll.get("status") in ("rejected", "fully_issued"):
        raise HTTPException(400, f"Roll berstatus '{roll['status']}' tidak dapat di-putaway")
    old_pos = roll.get("position_barcode", "")
    await db.wh_fabric_rolls.update_one({"id": roll_id}, {"$set": {
        "position_id": data.position_id,
        "position_barcode": data.position_barcode,
        "updated_at": _now(),
        "updated_by": user.get("name", user["id"]),
    }})
    await _log_movement(db, roll, "putaway", 0, roll.get("uom", "meter"),
                        "manual", "", "", old_pos, data.position_barcode,
                        data.notes or f"Put-away ke posisi {data.position_barcode}",
                        user.get("name", ""))
    return {"ok": True, "position_barcode": data.position_barcode}


@router.post("/{roll_id}/issue")
async def issue_roll(roll_id: str, data: IssueIn, request: Request):
    user = await require_auth(request)
    db = get_db()
    roll = await db.wh_fabric_rolls.find_one({"id": roll_id})
    if not roll:
        raise HTTPException(404, "Roll tidak ditemukan")
    if roll.get("status") in ("rejected", "fully_issued"):
        raise HTTPException(400, f"Roll berstatus '{roll['status']}' tidak dapat di-issue")
    # Satuan pengeluaran WAJIB satuan gulungan itu sendiri (2026-08-21).
    # Dulu embernya dipilih dari `data.unit`: gulungan YARD yang dikeluarkan
    # sebagai "meter" tetap mengurangi angka yard (label bohong), dan bila
    # pemakai memilih "kg" sistem menjawab "sisa 0" padahal gulungannya penuh.
    field = fabric_roll_engine.remaining_field(roll)
    r_uom = str(roll.get("uom") or "").strip().lower()
    d_uom = str(data.unit or "").strip().lower()
    if d_uom and r_uom and d_uom != r_uom:
        raise HTTPException(400, (
            f"Gulungan {roll.get('roll_no')} bersatuan {r_uom} — keluarkan dalam {r_uom}, "
            f"bukan {d_uom}."))
    remaining = roll.get(field, 0)
    if data.qty > remaining:
        raise HTTPException(400, f"Sisa hanya {remaining:.2f} {r_uom}. Issue {data.qty:.2f} melebihi sisa")
    new_remaining = remaining - data.qty
    new_status = _recalc_status({**roll, field: new_remaining})
    await db.wh_fabric_rolls.update_one({"id": roll_id}, {"$set": {
        field: new_remaining,
        "status": new_status,
        "updated_at": _now(),
        "updated_by": user.get("name", user["id"]),
    }})
    await _log_movement(db, roll, "issue", data.qty, r_uom or d_uom,
                        data.reference_type, data.reference_id, data.reference_no,
                        roll.get("position_barcode", ""), data.reference_no,
                        data.notes, user.get("name", ""))
    return {"ok": True, "issued_qty": data.qty, "remaining": new_remaining, "status": new_status}


@router.post("/{roll_id}/return")
async def return_roll(roll_id: str, data: ReturnIn, request: Request):
    user = await require_auth(request)
    db = get_db()
    roll = await db.wh_fabric_rolls.find_one({"id": roll_id})
    if not roll:
        raise HTTPException(404, "Roll tidak ditemukan")
    field = "remaining_m" if data.unit == "meter" else "remaining_kg"
    new_remaining = roll.get(field, 0) + data.qty
    new_status = _recalc_status({**roll, field: new_remaining})
    await db.wh_fabric_rolls.update_one({"id": roll_id}, {"$set": {
        field: new_remaining,
        "status": new_status,
        "updated_at": _now(),
        "updated_by": user.get("name", user["id"]),
    }})
    await _log_movement(db, roll, "return", data.qty, data.unit,
                        data.reference_type, data.reference_id, data.reference_no,
                        data.reference_no, roll.get("position_barcode", ""),
                        data.notes, user.get("name", ""))
    return {"ok": True, "returned_qty": data.qty, "remaining": new_remaining, "status": new_status}


@router.post("/{roll_id}/reject")
async def reject_roll(roll_id: str, data: RejectIn, request: Request):
    from routes.shared import require_perm
    user = await require_perm(
        request, 'warehouse.approve', 'warehouse.manage', 'inventory.manage',
        legacy_roles=('admin_gudang', 'spv_packing', 'supervisor', 'manager_produksi',
                      'supervisor_produksi', 'owner', 'admin', 'superadmin'),
        message='Akses ditolak: Anda tidak berhak menolak roll kain.')
    db = get_db()
    roll = await db.wh_fabric_rolls.find_one({"id": roll_id})
    if not roll:
        raise HTTPException(404, "Roll tidak ditemukan")
    if roll.get("status") == "rejected":
        raise HTTPException(400, "Roll sudah ditandai reject")
    await db.wh_fabric_rolls.update_one({"id": roll_id}, {"$set": {
        "status": "rejected",
        "qc_status": "reject",
        "reject_reason": data.reason,
        "claim_to_supplier": data.claim_to_supplier,
        "updated_at": _now(),
        "updated_by": user.get("name", user["id"]),
    }})
    await _log_movement(db, roll, "reject", roll.get("remaining_m", 0) or roll.get("remaining_kg", 0),
                        roll.get("uom", "meter"), "manual", "", "",
                        roll.get("position_barcode", ""), "rejected",
                        data.reason, user.get("name", ""))
    return {"ok": True, "status": "rejected", "claim": data.claim_to_supplier}


@router.post("/{roll_id}/adjust")
async def adjust_roll(roll_id: str, data: AdjustIn, request: Request):
    user = await require_auth(request)
    db = get_db()
    roll = await db.wh_fabric_rolls.find_one({"id": roll_id})
    if not roll:
        raise HTTPException(404, "Roll tidak ditemukan")
    new_m = max(0, roll.get("remaining_m", 0) + data.delta_m)
    new_kg = max(0, roll.get("remaining_kg", 0) + data.delta_kg)
    new_status = _recalc_status({**roll, "remaining_m": new_m, "remaining_kg": new_kg})
    await db.wh_fabric_rolls.update_one({"id": roll_id}, {"$set": {
        "remaining_m": new_m, "remaining_kg": new_kg, "status": new_status,
        "updated_at": _now(), "updated_by": user.get("name", user["id"]),
    }})
    qty = abs(data.delta_m) or abs(data.delta_kg)
    unit = "meter" if data.delta_m != 0 else "kg"
    await _log_movement(db, roll, "adjust", qty, unit, "manual", "", "",
                        "", "", data.reason, user.get("name", ""))
    return {"ok": True, "remaining_m": new_m, "remaining_kg": new_kg, "status": new_status}


@router.get("/{roll_id}/label-pdf")
async def roll_label_pdf(roll_id: str, request: Request, token: Optional[str] = None):
    from auth import verify_token_str
    if token:
        user = verify_token_str(token)
        if not user:
            raise HTTPException(401, "Invalid token")
    else:
        user = await require_auth(request)
    db = get_db()
    roll = await db.wh_fabric_rolls.find_one(
        {"$or": [{"id": roll_id}, {"roll_no": roll_id}]}, {"_id": 0})
    if not roll:
        raise HTTPException(404, "Roll tidak ditemukan")
    if not REPORTLAB_OK:
        raise HTTPException(500, "ReportLab tidak tersedia")

    buf = io.BytesIO()
    W, H = 90 * mm, 50 * mm
    c = canvas.Canvas(buf, pagesize=(W, H))
    # Header
    c.setFont("Helvetica-Bold", 9)
    c.drawString(3 * mm, H - 7 * mm, "CV. DEWI ADITYA")
    c.setFont("Helvetica", 7)
    c.drawString(3 * mm, H - 12 * mm, f"ROLL: {roll['roll_no']}")
    c.drawString(3 * mm, H - 17 * mm, f"{roll.get('material_name', '')} | {roll.get('color', '')}")
    c.drawString(3 * mm, H - 22 * mm, f"LOT: {roll.get('color_lot', '-')} | {roll.get('supplier_name', '')}")
    c.drawString(3 * mm, H - 27 * mm, f"{roll.get('length_m', 0):.1f}m / {roll.get('weight_kg', 0):.2f}kg")
    # Barcode
    try:
        barcode_buf = io.BytesIO()
        w = ImageWriter()
        Code128(roll["roll_no"], writer=w).write(barcode_buf, options={"module_width": 0.35, "module_height": 10.0, "quiet_zone": 2.0, "text_distance": 2.0, "font_size": 6, "write_text": True})
        barcode_buf.seek(0)
        img = PILImage.open(barcode_buf)
        img_buf = io.BytesIO()
        img.save(img_buf, "PNG")
        img_buf.seek(0)
        from reportlab.lib.utils import ImageReader
        c.drawImage(ImageReader(img_buf), 3 * mm, 5 * mm, width=84 * mm, height=16 * mm, preserveAspectRatio=True)
    except Exception as e:
        log.warning(f"Barcode generation failed: {e}")
    c.save()
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="roll-{roll["roll_no"]}.pdf"'},
    )


@router.delete("/{roll_id}")
async def delete_roll(roll_id: str, request: Request):
    await require_auth(request)
    db = get_db()
    roll = await db.wh_fabric_rolls.find_one({"id": roll_id})
    if not roll:
        raise HTTPException(404, "Roll tidak ditemukan")
    if roll.get("status") not in ("in_stock", "rejected"):
        raise HTTPException(400, "Hanya roll in_stock/rejected yang dapat dihapus")
    has_movements = await db.wh_fabric_roll_movements.count_documents({"roll_id": roll_id})
    if has_movements > 1:  # >1 karena ada log receive saat create
        raise HTTPException(400, "Roll sudah punya riwayat movement, tidak dapat dihapus")
    await db.wh_fabric_rolls.delete_one({"id": roll_id})
    await db.wh_fabric_roll_movements.delete_many({"roll_id": roll_id})
    return {"ok": True}
