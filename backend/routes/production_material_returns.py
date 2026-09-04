"""
Production Material Returns — Pengembalian Material dari Lantai Produksi ke Gudang
CV. Dewi Aditya — Task 2.5

Prefix: /api/production/material-returns

Alur:
  Production staff submit return → Supervisor produksi approve → Gudang receive → stok +

Colleciton: production_material_returns
"""
from fastapi import APIRouter, Request, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime, timezone
from database import get_db
from auth import require_auth, log_activity
from utils.counters import next_counter, gen_prefixed_number
from core import stock_service
import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/production/material-returns", tags=["production-material-returns"])


def _coerce_id(id_str: str):
    """Coba konversi ke int, fallback ke string untuk MongoDB lookup."""
    try:
        return int(id_str)
    except (ValueError, TypeError):
        return id_str


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ─── Pydantic ─────────────────────────────────────────────────────────────────

class ReturnItem(BaseModel):
    material_id: str = ""
    material_code: str = ""
    material_name: str = ""
    qty_returned: float = Field(ge=0)
    unit: str = "pcs"
    reason: str = "sisa_produksi"   # sisa_produksi | rusak | salah_material
    condition: str = "good"          # good | damaged | scrap
    note: str = ""


class ReturnCreateModel(BaseModel):
    work_order_id: str = ""
    work_order_code: str = ""
    production_line: str = ""
    return_reason: str = ""          # alasan umum
    notes: str = ""
    items: List[ReturnItem] = Field(default_factory=list)


class ReturnUpdateModel(BaseModel):
    notes: Optional[str] = None
    items: Optional[List[ReturnItem]] = None
    return_reason: Optional[str] = None


class ActionModel(BaseModel):
    note: str = ""


# ─── Helper ───────────────────────────────────────────────────────────────────

def _ok(data=None, message="", **kwargs):
    r = {"status": "ok"}
    if message:
        r["message"] = message
    if data is not None:
        r["data"] = data
    r.update(kwargs)
    return r


async def _build_ref(db) -> str:
    prefix = f"PMR/{datetime.now(timezone.utc).strftime('%Y/%m/')}"
    # RC-5 fix: atomic race-safe numbering (was count_documents()+1)
    # SESI #27 — jenis dokumen ini SENGAJA tidak ada di katalog penomoran: menu
    # "Retur Material" sudah di-deprecate pemilik (material diurus lewat "Kirim
    # Material CMT") sehingga tidak ada layar yang membuatnya. Tercatat sebagai
    # pengecualian beralasan di gate INV-F25 (G12) — bukan dilupakan.
    return await gen_prefixed_number(db, "production_material_returns", "ref_no", prefix, 4)


# ─── Endpoints ────────────────────────────────────────────────────────────────

@router.get("")
async def list_returns(
    request: Request,
    status: Optional[str] = None,
    work_order_id: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    skip: int = Query(0, ge=0),
):
    await require_auth(request)
    db = get_db()
    q = {}
    if status:
        q["status"] = status
    if work_order_id:
        q["work_order_id"] = work_order_id
    total = await db.production_material_returns.count_documents(q)
    items = await db.production_material_returns.find(q, {"_id": 0}).sort("created_at", -1).skip(skip).limit(limit).to_list(limit)
    return _ok(items, total=total, skip=skip, limit=limit)


@router.post("")
async def create_return(request: Request, body: ReturnCreateModel):
    user = await require_auth(request)
    db = get_db()
    ref_no = await _build_ref(db)
    doc_id = await next_counter(db, "production_material_returns")
    now = _now()
    doc = {
        "id": doc_id,
        "ref_no": ref_no,
        "work_order_id": body.work_order_id,
        "work_order_code": body.work_order_code,
        "production_line": body.production_line,
        "return_reason": body.return_reason,
        "notes": body.notes,
        "items": [i.dict() for i in body.items],
        "status": "draft",
        "submitted_by": user.get("full_name") or user.get("email") or "",
        "submitted_by_id": str(user.get("id") or user.get("_id") or ""),
        "approved_by": None,
        "approved_at": None,
        "received_by": None,
        "received_at": None,
        "created_at": now,
        "updated_at": now,
    }
    await db.production_material_returns.insert_one({"_id": doc_id, **doc})
    await log_activity(
        str(user.get("id") or user.get("_id") or ""),
        user.get("full_name") or user.get("name") or user.get("email") or "",
        "create",
        "production_material_returns",
        f"Return {ref_no} created: {doc_id}"
    )
    return _ok(doc, message=f"Return {ref_no} berhasil dibuat.")


@router.get("/summary")
async def returns_summary(request: Request):
    await require_auth(request)
    db = get_db()
    statuses = ["draft", "submitted", "approved", "received", "rejected"]
    summary = {}
    for s in statuses:
        summary[s] = await db.production_material_returns.count_documents({"status": s})
    return _ok(summary)


@router.get("/{return_id}")
async def get_return(request: Request, return_id: str):
    await require_auth(request)
    db = get_db()
    doc = await db.production_material_returns.find_one({"id": _coerce_id(return_id)}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Return tidak ditemukan.")
    return _ok(doc)


@router.put("/{return_id}")
async def update_return(request: Request, return_id: str, body: ReturnUpdateModel):
    await require_auth(request)
    db = get_db()
    doc = await db.production_material_returns.find_one({"id": _coerce_id(return_id)})
    if not doc:
        raise HTTPException(404, "Return tidak ditemukan.")
    if doc.get("status") not in ("draft",):
        raise HTTPException(400, "Hanya return dengan status draft yang bisa diedit.")
    update = {k: v for k, v in body.dict(exclude_none=True).items()}
    if "items" in update:
        update["items"] = [i.dict() if hasattr(i, 'dict') else i for i in update["items"]]
    update["updated_at"] = _now()
    await db.production_material_returns.update_one({"id": _coerce_id(return_id)}, {"$set": update})
    return _ok(message="Return berhasil diupdate.")


@router.post("/{return_id}/submit")
async def submit_return(request: Request, return_id: str):
    """Ubah status dari draft → submitted untuk dikirim ke supervisor."""
    user = await require_auth(request)
    db = get_db()
    doc = await db.production_material_returns.find_one({"id": _coerce_id(return_id)})
    if not doc:
        raise HTTPException(404, "Return tidak ditemukan.")
    if doc.get("status") != "draft":
        raise HTTPException(400, f"Status saat ini: {doc.get('status')}. Hanya draft yang bisa disubmit.")
    if not doc.get("items"):
        raise HTTPException(400, "Tambahkan minimal 1 item sebelum submit.")

    # ── Task 2.5: Validasi qty return tidak melebihi yang pernah dikeluarkan ─────
    wo_id = doc.get("work_order_id")
    if wo_id:
        all_issues = await db.rahaza_material_issues.find(
            {"work_order_id": wo_id, "status": {"$in": ["approved", "issued"]}},
            {"_id": 0, "items": 1}
        ).to_list(200)
        if all_issues:
            issued_map: dict = {}
            for mi in all_issues:
                for mi_item in (mi.get("items") or []):
                    code = (mi_item.get("material_code") or "").strip()
                    if code:
                        issued_map[code] = issued_map.get(code, 0) + float(mi_item.get("qty_issued") or 0)
            # Total yang sudah pernah direturn (di luar dokumen ini)
            existing = await db.production_material_returns.find(
                {
                    "work_order_id": wo_id,
                    "status": {"$in": ["submitted", "approved", "received"]},
                    "id": {"$ne": _coerce_id(return_id)},
                },
                {"_id": 0, "items": 1}
            ).to_list(200)
            returned_map: dict = {}
            for ret in existing:
                for r_item in (ret.get("items") or []):
                    code = (r_item.get("material_code") or "").strip()
                    if code:
                        returned_map[code] = returned_map.get(code, 0) + float(r_item.get("qty_returned") or 0)
            errors = []
            for ret_item in doc.get("items", []):
                code = (ret_item.get("material_code") or "").strip()
                qty  = float(ret_item.get("qty_returned") or 0)
                if code in issued_map and qty > 0:
                    available = issued_map[code] - returned_map.get(code, 0)
                    if qty > available + 0.001:
                        errors.append(f"'{code}': return {qty} > tersedia {max(0, available):.2f}")
            if errors:
                raise HTTPException(400, f"Qty return melebihi jumlah yang dikeluarkan: {'; '.join(errors)}")

    now = _now()
    await db.production_material_returns.update_one(
        {"id": _coerce_id(return_id)},
        {"$set": {"status": "submitted", "submitted_at": now, "updated_at": now}},
    )
    await log_activity(
        str(user.get("id") or user.get("_id") or ""),
        user.get("full_name") or user.get("name") or user.get("email") or "",
        "submit",
        "production_material_returns",
        f"Return {return_id} submitted"
    )
    return _ok(message="Return berhasil disubmit, menunggu persetujuan supervisor.")


@router.post("/{return_id}/approve")
async def approve_return(request: Request, return_id: str, body: ActionModel):
    """Supervisor produksi menyetujui return."""
    user = await require_auth(request)
    role = (user.get("role") or "").lower()
    if role not in ("superadmin", "admin", "owner", "manager"):
        raise HTTPException(403, "Hanya supervisor/manager yang dapat menyetujui.")
    db = get_db()
    doc = await db.production_material_returns.find_one({"id": _coerce_id(return_id)})
    if not doc:
        raise HTTPException(404, "Return tidak ditemukan.")
    if doc.get("status") != "submitted":
        raise HTTPException(400, "Hanya return submitted yang bisa disetujui.")
    now = _now()
    await db.production_material_returns.update_one(
        {"id": _coerce_id(return_id)},
        {"$set": {
            "status": "approved",
            "approved_by": user.get("full_name") or user.get("email") or "",
            "approved_by_id": str(user.get("id") or user.get("_id") or ""),
            "approved_at": now,
            "approve_note": body.note,
            "updated_at": now,
        }},
    )
    await log_activity(
        str(user.get("id") or user.get("_id") or ""),
        user.get("full_name") or user.get("name") or user.get("email") or "",
        "approve",
        "production_material_returns",
        f"Return {return_id} approved: {body.note}"
    )
    return _ok(message="Return disetujui. Menunggu penerimaan di gudang.")


@router.post("/{return_id}/reject")
async def reject_return(request: Request, return_id: str, body: ActionModel):
    user = await require_auth(request)
    role = (user.get("role") or "").lower()
    if role not in ("superadmin", "admin", "owner", "manager"):
        raise HTTPException(403, "Hanya supervisor/manager yang dapat menolak.")
    db = get_db()
    doc = await db.production_material_returns.find_one({"id": _coerce_id(return_id)})
    if not doc:
        raise HTTPException(404, "Return tidak ditemukan.")
    if doc.get("status") not in ("submitted",):
        raise HTTPException(400, "Hanya return submitted yang bisa ditolak.")
    now = _now()
    await db.production_material_returns.update_one(
        {"id": _coerce_id(return_id)},
        {"$set": {"status": "rejected", "reject_note": body.note, "updated_at": now}},
    )
    await log_activity(
        str(user.get("id") or user.get("_id") or ""),
        user.get("full_name") or user.get("name") or user.get("email") or "",
        "reject",
        "production_material_returns",
        f"Return {return_id} rejected: {body.note}"
    )
    return _ok(message="Return ditolak.")


@router.post("/{return_id}/receive")
async def receive_return(request: Request, return_id: str, body: ActionModel):
    """Gudang menerima material return dan update stok."""
    user = await require_auth(request)
    db = get_db()
    doc = await db.production_material_returns.find_one({"id": _coerce_id(return_id)}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Return tidak ditemukan.")
    if doc.get("status") != "approved":
        raise HTTPException(400, "Return harus disetujui supervisor sebelum diterima gudang.")
    now = _now()
    # Update stok: tambah kembali qty ke rahaza_material_stock
    items = doc.get("items", [])
    default_loc = await db.rahaza_locations.find_one({"active": True}, {"_id": 0})
    loc_id = default_loc["id"] if default_loc else None
    for item in items:
        mat_id = item.get("material_id")
        qty = float(item.get("qty_returned", 0))
        condition = item.get("condition", "good")
        if not mat_id or qty <= 0:
            continue
        if condition in ("good", "scrap"):   # 'damaged' tidak kembali ke stok
            # INV-6 FIX: kembalikan stok via stock_service (qty kanonik + alias + available),
            # bukan field hantu qty_available/qty_on_hand tanpa lokasi. Hanya 'good' yang jadi
            # stok siap pakai; 'scrap' hanya dicatat movement (tidak masuk stok usable).
            if condition == "good" and loc_id:
                mat = await db.rahaza_materials.find_one({"id": mat_id}, {"_id": 0})
                mtype = ((mat or {}).get("type") or "").lower()
                await stock_service.add(
                    mat_id, loc_id, qty,
                    meta={
                        "material_type": mtype or None,
                        "material_code": item.get("material_code"),
                        "material_name": item.get("material_name"),
                        "ownership": "cv_da",
                        "inventory_category": "fg_internal" if mtype == "fg" else "raw_material",
                    },
                    ref={"source": "production_return", "return_id": str(return_id),
                         "ref_code": doc.get("ref_no", ""), "condition": condition},
                    actor={"id": str(user.get("id") or ""), "email": user.get("email", "")},
                    db=db,
                )
            # Catat movement (audit) — semua kondisi good/scrap
            await db.rahaza_material_movements.insert_one({
                "material_id": mat_id,
                "material_code": item.get("material_code", ""),
                "material_name": item.get("material_name", ""),
                "movement_type": "production_return",
                "qty": qty,
                "condition": condition,
                "ref_id": return_id,
                "ref_code": doc.get("ref_no", ""),
                "note": f"Return dari produksi ({condition}): {body.note or 'received'}",
                "created_at": now,
            })
    await db.production_material_returns.update_one(
        {"id": _coerce_id(return_id)},
        {"$set": {
            "status": "received",
            "received_by": user.get("full_name") or user.get("email") or "",
            "received_by_id": str(user.get("id") or user.get("_id") or ""),
            "received_at": now,
            "receive_note": body.note,
            "updated_at": now,
        }},
    )
    await log_activity(
        str(user.get("id") or user.get("_id") or ""),
        user.get("full_name") or user.get("name") or user.get("email") or "",
        "receive",
        "production_material_returns",
        f"Return {return_id} received: {len(items)} items"
    )
    return _ok(message=f"Material return diterima. {len(items)} item dikembalikan ke stok.")


@router.delete("/{return_id}")
async def delete_return(request: Request, return_id: str):
    await require_auth(request)
    db = get_db()
    doc = await db.production_material_returns.find_one({"id": _coerce_id(return_id)})
    if not doc:
        raise HTTPException(404, "Return tidak ditemukan.")
    if doc.get("status") not in ("draft",):
        raise HTTPException(400, "Hanya draft yang bisa dihapus.")
    await db.production_material_returns.delete_one({"id": _coerce_id(return_id)})
    return _ok(message="Return dihapus.")
