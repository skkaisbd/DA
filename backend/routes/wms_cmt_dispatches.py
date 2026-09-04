"""
WMS — CMT Material Disbursement (P1-WH-1)
CV. Dewi Aditya — Tracking material keluar ke CMT per Work Order

Collection: wh_cmt_dispatches
  id, dispatch_no (CMD/2026/05/0001), wo_id, wo_number, cmt_name, cmt_address,
  status (draft|dispatched|partially_returned|fully_returned|cancelled),
  sj_id (link ke Surat Jalan),
  lines: [{material_id, material_code, material_name, roll_nos[], qty, unit,
           qty_returned, unit_cost, remarks}],
  dispatched_at, returned_at, notes,
  created_at, created_by, updated_at, updated_by

Endpoints (prefix /api/wms/cmt-dispatches):
  GET    /                     list + filters
  POST   /                     create new dispatch
  GET    /{dispatch_id}        detail + lines
  PUT    /{dispatch_id}        update draft
  POST   /{dispatch_id}/dispatch   execute dispatch (create SJ-CMT automatically)
  POST   /{dispatch_id}/return-line   record return of materials from CMT
  POST   /{dispatch_id}/cancel
  GET    /by-wo/{wo_id}        all dispatches for a WO
"""
import uuid
from datetime import datetime, timezone
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Request, Query
from pydantic import BaseModel, Field
from database import get_db
from utils.counters import gen_prefixed_number
from auth import require_auth, serialize_doc
import logging

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/wms/cmt-dispatches", tags=["wms-cmt"])

DISPATCH_STATUSES = ["draft", "dispatched", "partially_returned", "fully_returned", "cancelled"]


def _now(): return datetime.now(timezone.utc)
def _id(): return str(uuid.uuid4())


class DispatchLine(BaseModel):
    material_id: str = ""
    material_code: str
    material_name: str
    roll_nos: List[str] = []
    qty: float = Field(..., gt=0)
    unit: str = "meter"
    unit_cost: float = Field(default=0.0, ge=0)
    remarks: str = ""


class DispatchIn(BaseModel):
    wo_id: str = ""
    wo_number: str = ""
    cmt_name: str = Field(..., min_length=1)
    cmt_address: str = ""
    delivery_date: Optional[str] = None
    notes: str = ""
    lines: List[DispatchLine] = []


class ReturnLineIn(BaseModel):
    material_code: str
    qty_returned: float = Field(..., gt=0)
    unit: str = "meter"
    notes: str = ""


async def _next_dispatch_no(db) -> str:
    prefix = f"CMD/{_now().strftime('%Y/%m')}/"
    # RC-5 fix: atomic race-safe numbering (was count_documents()+1 -> dup/E11000)
    return await gen_prefixed_number(db, "wh_cmt_dispatches", "dispatch_no", prefix, 4)


@router.get("")
async def list_dispatches(
    request: Request,
    status: Optional[str] = None,
    cmt_name: Optional[str] = None,
    wo_id: Optional[str] = None,
    search: Optional[str] = None,
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
):
    await require_auth(request)
    db = get_db()
    q = {}
    if status:
        q["status"] = status
    if cmt_name:
        q["cmt_name"] = {"$regex": cmt_name, "$options": "i"}
    if wo_id:
        q["wo_id"] = wo_id
    if search:
        q["$or"] = [
            {"dispatch_no": {"$regex": search, "$options": "i"}},
            {"cmt_name": {"$regex": search, "$options": "i"}},
            {"wo_number": {"$regex": search, "$options": "i"}},
        ]
    total = await db.wh_cmt_dispatches.count_documents(q)
    skip = (page - 1) * limit
    items = await db.wh_cmt_dispatches.find(q, {"_id": 0}).sort("created_at", -1).skip(skip).limit(limit).to_list(limit)
    return {
        "items": [serialize_doc(i) for i in items],
        "pagination": {
            "page": page, "limit": limit, "total": total,
            "total_pages": max(1, (total + limit - 1) // limit),
            "has_next": (skip + limit) < total,
            "has_prev": page > 1,
        }
    }


@router.post("")
async def create_dispatch(data: DispatchIn, request: Request):
    user = await require_auth(request)
    db = get_db()
    dispatch_id = _id()
    now = _now()
    dispatch_no = await _next_dispatch_no(db)
    lines = []
    for i, ln in enumerate(data.lines):
        lines.append({
            "line_no": i + 1,
            **ln.dict(),
            "qty_returned": 0.0,
            "qty_outstanding": ln.qty,
        })
    doc = {
        "id": dispatch_id,
        "dispatch_no": dispatch_no,
        "wo_id": data.wo_id,
        "wo_number": data.wo_number,
        "cmt_name": data.cmt_name,
        "cmt_address": data.cmt_address,
        "delivery_date": data.delivery_date or now.date().isoformat(),
        "status": "draft",
        "sj_id": None,
        "sj_number": "",
        "lines": lines,
        "notes": data.notes,
        "dispatched_at": None,
        "returned_at": None,
        "created_at": now,
        "created_by": user.get("name", user["id"]),
        "updated_at": now,
        "updated_by": user.get("name", user["id"]),
    }
    await db.wh_cmt_dispatches.insert_one(doc)
    out = await db.wh_cmt_dispatches.find_one({"id": dispatch_id}, {"_id": 0})
    return {"ok": True, "dispatch": serialize_doc(out)}


@router.get("/by-wo/{wo_id}")
async def dispatches_by_wo(wo_id: str, request: Request):
    await require_auth(request)
    db = get_db()
    items = await db.wh_cmt_dispatches.find({"wo_id": wo_id}, {"_id": 0}).sort("created_at", -1).to_list(50)
    return [serialize_doc(i) for i in items]


@router.get("/{dispatch_id}")
async def get_dispatch(dispatch_id: str, request: Request):
    await require_auth(request)
    db = get_db()
    item = await db.wh_cmt_dispatches.find_one(
        {"$or": [{"id": dispatch_id}, {"dispatch_no": dispatch_id}]}, {"_id": 0})
    if not item:
        raise HTTPException(404, "Dispatch tidak ditemukan")
    return serialize_doc(item)


@router.put("/{dispatch_id}")
async def update_dispatch(dispatch_id: str, data: dict, request: Request):
    user = await require_auth(request)
    db = get_db()
    item = await db.wh_cmt_dispatches.find_one({"id": dispatch_id})
    if not item:
        raise HTTPException(404, "Dispatch tidak ditemukan")
    if item["status"] != "draft":
        raise HTTPException(400, "Hanya draft yang dapat diupdate")
    allowed = {"cmt_name", "cmt_address", "delivery_date", "notes", "lines", "wo_id", "wo_number"}
    updates = {k: v for k, v in data.items() if k in allowed}
    if "lines" in updates:
        updates["lines"] = [{"line_no": i + 1, "qty_returned": 0.0, "qty_outstanding": ln.get("qty", 0), **{k: v for k, v in ln.items() if k not in ("line_no", "qty_returned", "qty_outstanding")}} for i, ln in enumerate(updates["lines"])]
    updates["updated_at"] = _now()
    updates["updated_by"] = user.get("name", user["id"])
    await db.wh_cmt_dispatches.update_one({"id": dispatch_id}, {"$set": updates})
    out = await db.wh_cmt_dispatches.find_one({"id": dispatch_id}, {"_id": 0})
    return {"ok": True, "dispatch": serialize_doc(out)}


@router.post("/{dispatch_id}/dispatch")
async def execute_dispatch(dispatch_id: str, request: Request, body: dict = {}):
    """Execute dispatch: change status to dispatched + auto-create SJ-CMT."""
    user = await require_auth(request)
    db = get_db()
    item = await db.wh_cmt_dispatches.find_one({"id": dispatch_id})
    if not item:
        raise HTTPException(404, "Dispatch tidak ditemukan")
    if item["status"] != "draft":
        raise HTTPException(400, "Hanya draft yang dapat di-dispatch")
    if not item.get("lines"):
        raise HTTPException(400, "Minimal 1 item diperlukan")

    # Auto-create Surat Jalan CMT
    from routes.wms_delivery_notes import _next_sj_number
    sj_id = str(uuid.uuid4())
    now = _now()
    sj_number = await _next_sj_number(db, "SJ-CMT")
    sj_lines = []
    for i, ln in enumerate(item.get("lines", [])):
        desc = f"{ln.get('material_name', ln.get('material_code', ''))} {' '.join(ln.get('roll_nos', [])[:3])}".strip()
        sj_lines.append({"line_no": i + 1, "description": desc, "qty": ln["qty"],
                          "unit": ln.get("unit", "meter"), "remarks": ln.get("remarks", ""),
                          "roll_no": ", ".join(ln.get("roll_nos", []))[:50],
                          "material_code": ln.get("material_code", "")})
    sj_doc = {
        "id": sj_id,
        "sj_number": sj_number,
        "sj_type": "SJ-CMT",
        "status": "issued",
        "recipient_name": item["cmt_name"],
        "recipient_address": item.get("cmt_address", ""),
        "recipient_phone": "",
        "shipper_name": body.get("shipper_name", ""),
        "vehicle_no": body.get("vehicle_no", ""),
        "notes": item.get("notes", ""),
        "reference_type": "wo",
        "reference_id": item.get("wo_id", ""),
        "reference_no": item.get("wo_number", item.get("dispatch_no", "")),
        "lines": sj_lines,
        "issued_at": now,
        "received_at": None, "cancelled_at": None,
        "created_at": now,
        "created_by": user.get("name", user["id"]),
        "updated_at": now,
        "updated_by": user.get("name", user["id"]),
    }
    await db.wh_delivery_notes.insert_one(sj_doc)
    await db.wh_cmt_dispatches.update_one({"id": dispatch_id}, {"$set": {
        "status": "dispatched",
        "sj_id": sj_id,
        "sj_number": sj_number,
        "dispatched_at": now,
        "updated_at": now,
        "updated_by": user.get("name", user["id"]),
    }})

    # WS-E: buat PENDING OUTBOUND_RM per line (best-effort). Stok BELUM turun —
    # gudang wajib Scan-Out di WMS sebelum stok material berkurang.
    pendings = []
    try:
        from routes.wms_receiving import helper_create_pending_outbound_rm
        for ln in item.get("lines", []):
            mat_id = ln.get("material_id") or ""
            if not mat_id and ln.get("material_code"):
                mat = await db.rahaza_materials.find_one({"code": ln.get("material_code")}, {"_id": 0})
                mat_id = mat.get("id") if mat else ""
            if not mat_id:
                continue  # tak ter-resolve → dokumen SJ saja, stok tak disentuh
            pending = await helper_create_pending_outbound_rm(
                db,
                material_id=mat_id,
                material_code=ln.get("material_code", ""),
                material_name=ln.get("material_name", ""),
                qty=float(ln.get("qty", 0) or 0),
                unit=ln.get("unit", "meter"),
                source_type="cmt_dispatch",
                source_id=dispatch_id,
                source_ref=item.get("dispatch_no", ""),
                notes=f"Kirim ke CMT {item.get('cmt_name','')} — Scan-Out diperlukan",
                created_by=user.get("email", user.get("name", "system")),
            )
            pendings.append({"pending_id": pending.get("id"), "ref_number": pending.get("ref_number"),
                             "material_name": ln.get("material_name", ""), "qty": ln.get("qty", 0)})
        if pendings:
            await db.wh_cmt_dispatches.update_one(
                {"id": dispatch_id},
                {"$set": {"wms_pending_refs": [p["ref_number"] for p in pendings]}}
            )
    except Exception as e:
        log.warning(f"Gagal buat pending outbound_rm CMT dispatch {dispatch_id}: {e}")

    out = await db.wh_cmt_dispatches.find_one({"id": dispatch_id}, {"_id": 0})
    return {"ok": True, "dispatch": serialize_doc(out), "sj_number": sj_number,
            "wms_pending": pendings, "scan_out_required": bool(pendings)}


@router.post("/{dispatch_id}/return-line")
async def return_materials(dispatch_id: str, data: ReturnLineIn, request: Request):
    user = await require_auth(request)
    db = get_db()
    item = await db.wh_cmt_dispatches.find_one({"id": dispatch_id})
    if not item:
        raise HTTPException(404, "Dispatch tidak ditemukan")
    if item["status"] not in ("dispatched", "partially_returned"):
        raise HTTPException(400, "Dispatch harus berstatus dispatched atau partially_returned")

    lines = item.get("lines", [])
    updated = False
    for ln in lines:
        if ln.get("material_code") == data.material_code:
            ln["qty_returned"] = ln.get("qty_returned", 0) + data.qty_returned
            ln["qty_outstanding"] = max(0, ln.get("qty", 0) - ln["qty_returned"])
            updated = True
            break
    if not updated:
        raise HTTPException(404, f"Material {data.material_code} tidak ada di dispatch")

    all_returned = all(ln.get("qty_outstanding", 1) <= 0 for ln in lines)
    new_status = "fully_returned" if all_returned else "partially_returned"
    await db.wh_cmt_dispatches.update_one({"id": dispatch_id}, {"$set": {
        "lines": lines, "status": new_status,
        "returned_at": _now() if all_returned else None,
        "updated_at": _now(), "updated_by": user.get("name", user["id"]),
    }})
    out = await db.wh_cmt_dispatches.find_one({"id": dispatch_id}, {"_id": 0})
    return {"ok": True, "dispatch": serialize_doc(out)}


@router.post("/{dispatch_id}/cancel")
async def cancel_dispatch(dispatch_id: str, request: Request, body: dict = {}):
    user = await require_auth(request)
    db = get_db()
    item = await db.wh_cmt_dispatches.find_one({"id": dispatch_id})
    if not item:
        raise HTTPException(404, "Dispatch tidak ditemukan")
    if item["status"] in ("fully_returned",):
        raise HTTPException(400, "Tidak dapat membatalkan yang sudah selesai")
    await db.wh_cmt_dispatches.update_one({"id": dispatch_id}, {"$set": {
        "status": "cancelled", "cancel_reason": body.get("reason", ""),
        "updated_at": _now(), "updated_by": user.get("name", user["id"]),
    }})
    return {"ok": True}
