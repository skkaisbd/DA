"""
Dewi Accessories - Items
Items CRUD (SSOT: rahaza_materials)
"""
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
import uuid
import logging
from datetime import datetime, timezone
from database import get_db
from core.stock_schema import read_qty, inc_all_qty
from core import uom  # SSOT konversi satuan (multi-UOM berjenjang)
from utils.counters import gen_prefixed_number
from auth import require_auth, serialize_doc

_log = logging.getLogger(__name__)

router = APIRouter(tags=["accessories-items"])

# ── helpers ──────────────────────────────────────────────────────────────────
def _id():    return str(uuid.uuid4())
def _now_iso(): return datetime.now(timezone.utc).isoformat()
def _now():   return datetime.now(timezone.utc)

_VALID_UNITS = {
    "m", "cm", "yard", "inch",
    "kg", "gram", "ton",
    "pcs", "lusin", "kodi", "gross", "helai", "set", "pair",
    "rol", "gulung", "bal", "karton", "pak", "sak",
    "liter", "ml",
}

def _normalize_unit(unit: str) -> str:
    if not unit:
        return "pcs"
    u = str(unit).strip().lower()
    aliases = {
        "piece": "pcs", "pieces": "pcs", "buah": "pcs",
        "meter": "m", "centimeter": "cm",
        "kilogram": "kg", "gr": "gram", "grams": "gram",
        "pasang": "pair", "set/pair": "set",
        "rolls": "rol", "roll": "rol",
        "pack": "pak", "packs": "pak",
        "karton/dus": "karton", "dus": "karton",
    }
    u = aliases.get(u, u)
    return u if u in _VALID_UNITS else "pcs"

# Fase 2.8: helper stok aksesoris KANONIK dipindah ke core.accessory_stock
# (satukan ke rahaza_material_stock flat via stock_service; hilangkan duplikasi Schema-B nested).
from core.accessory_stock import (  # noqa: E402
    get_accessory_location_id as _get_accessory_location_id,
    stock_qty as _stock_qty,
    all_accessory_stock as _all_accessory_stock,
    add_stock as _add_stock,
)

async def _log_movement(db, user: dict, *, material_id: str, mv_type: str, qty: float,
                        notes: str = "", related_ref: str = "", related_type: str = ""):
    mat = await db.rahaza_materials.find_one(
        {"id": material_id}, {"_id": 0, "id": 1, "code": 1, "name": 1, "type": 1, "unit": 1}
    )
    if not mat:
        return
    loc_id = await _get_accessory_location_id(db)
    mvdoc = {
        "id": _id(),
        "material_id": material_id,
        "material": mat,
        "movement_type": mv_type,
        "qty_signed": qty,
        "location": {"id": loc_id, "code": "ZNA-AKSESORIS", "name": "Area Aksesoris"},
        "notes": notes,
        "reference_type": related_type,
        "reference_id": related_ref,
        "created_by": user.get("id", ""),
        "created_at": _now(),
    }
    await db.rahaza_material_movements.insert_one(mvdoc)

async def _enrich_movement(db, mv: dict) -> dict:
    """Lengkapi baris kartu stok dengan konteks permintaan/pinjaman — SSOT SAJA.

    FASE 10: sebelumnya membaca `acc_internal_requests` & `acc_loans` (koleksi legacy
    yang akan di-drop). Sekarang membaca SSOT: `dewi_accessory_requests` untuk
    permintaan internal dan `dewi_asset_loans` untuk peminjaman alat.
    """
    if mv.get("related_req_id"):
        req = await db.dewi_accessory_requests.find_one(
            {"id": mv["related_req_id"]},
            {"_id": 0, "request_code": 1, "divisi": 1, "request_type": 1},
        )
        if req:
            mv["related_request"] = {
                "request_number": req.get("request_code", ""),
                "division": req.get("divisi", ""),
            }
    if mv.get("related_loan_id"):
        loan = await db.dewi_asset_loans.find_one(
            {"id": mv["related_loan_id"]},
            {"_id": 0, "loan_number": 1, "borrower_name": 1},
        )
        if loan:
            mv["related_loan"] = loan
    return mv

def _material_to_acc_item(mat: dict, stock_qty: float = 0.0) -> dict:
    # Pack conversion for display
    pack_size = mat.get("pack_size", 1)
    if pack_size <= 0:
        pack_size = 1
    pack_unit = mat.get("pack_unit", "pack")
    display_in_packs = mat.get("display_in_packs", False)
    _min_stock = float(mat.get("min_stock") or 0)
    _unit_cost = float(mat.get("unit_cost") or mat.get("hpp") or 0)

    return {
        "id": mat.get("id", ""),
        "code": mat.get("code", ""),
        "name": mat.get("name", ""),
        "description": mat.get("description", ""),
        "unit": mat.get("unit", "pcs"),
        "color": mat.get("color", ""),
        "category": mat.get("category", ""),
        "min_stock": mat.get("min_stock", 0),
        "max_stock": mat.get("max_stock", 0),
        "stock_qty": stock_qty,
        # REGRESI FIX: status stok hilang saat refactor (FE menampilkan semua "Habis")
        "stock_status": ("out" if stock_qty <= 0
                        else "low" if (_min_stock > 0 and stock_qty <= _min_stock)
                        else "ok"),
        # FASE G+: harga satuan (dasar valuasi & posting JE selisih opname)
        "unit_cost": float(mat.get("unit_cost") or mat.get("hpp") or 0),
        "stock_value": round(stock_qty * float(mat.get("unit_cost") or mat.get("hpp") or 0), 2),
        # NEW: Pack info
        "pack_unit": pack_unit,
        "pack_size": pack_size,
        "display_in_packs": display_in_packs,
        "stock_qty_in_packs": round(stock_qty / pack_size, 2) if pack_size > 0 else stock_qty,
        "min_stock_in_packs": round(mat.get("min_stock", 0) / pack_size, 2) if pack_size > 0 else mat.get("min_stock", 0),
        # Multi-UOM (berjenjang) — SSOT core/uom. Field lama di atas tetap ada
        # sebagai cermin supaya klien lama tidak pecah (INV-UOM-4).
        "base_uom": uom.base_uom_of(mat),
        "uoms": uom.resolve_uoms(mat),
        "purchase_uom": uom.purchase_uom_of(mat),
        "issue_uom": uom.issue_uom_of(mat),
        "display_uom": uom.display_uom_of(mat),
        "stock_display": uom.format_dual(mat, stock_qty),
        "active": mat.get("active", True),
        "tags": mat.get("tags", []),
        "created_at": mat.get("created_at", _now_iso()),
    }

@router.get("/items")
async def list_items(request: Request):
    await require_auth(request)
    db = get_db()
    sp = request.query_params
    query: dict = {"type": "accessory", "active": True}
    if sp.get("search"):
        import re
        rx = re.compile(re.escape(sp["search"]), re.IGNORECASE)
        query["$or"] = [{"name": rx}, {"code": rx}, {"category": rx}]
    if sp.get("category"):
        query["category"] = sp["category"]

    mats = await db.rahaza_materials.find(query, {"_id": 0}).sort("name", 1).to_list(2000)
    stock_map = await _all_accessory_stock(db)
    items = [_material_to_acc_item(m, stock_map.get(m["id"], 0.0)) for m in mats]
    return serialize_doc(items)


@router.post("/items")
async def create_item(request: Request):
    user = await require_auth(request)
    db = get_db()
    body = await request.json()
    name = (body.get("name") or "").strip()
    if not name:
        raise HTTPException(400, "name wajib diisi")

    # RC-5 fix: atomic race-safe numbering (was count_documents()+1)
    code = (body.get("code") or await gen_prefixed_number(db, "rahaza_materials", "code", "ACC-", 4)).strip().upper()

    # Duplicate code guard (only within accessory namespace + active)
    if await db.rahaza_materials.find_one({"code": code, "type": "accessory", "active": True}):
        raise HTTPException(409, f"Kode '{code}' sudah terpakai untuk aksesoris.")

    unit = _normalize_unit(body.get("unit") or "pcs")

    # Satuan & kemasan — divalidasi + dinormalkan terpusat di core/uom.
    # Mengembalikan `uoms` + cermin field lama (pack_unit/pack_size/
    # display_in_packs) sehingga kode lama tetap bekerja (INV-UOM-4).
    try:
        uom_patch = uom.apply_payload({**body, "unit": unit})
    except uom.UomError as e:
        raise HTTPException(400, f"Satuan tidak valid: {e}")

    doc = {
        "id": _id(),
        "code": code,
        "name": name,
        "type": "accessory",
        "unit": unit,
        "category": (body.get("category") or "Umum"),
        "description": body.get("description", ""),
        "min_stock": float(body.get("min_stock") or 0),
        # FASE G+: harga satuan wajib agar selisih opname bisa dinilai & posting ke keuangan
        "unit_cost": float(body.get("unit_cost") or body.get("hpp") or 0),
        "supplier": body.get("supplier", ""),
        "notes": body.get("notes", ""),
        # Satuan & kemasan (uoms + cermin pack_*) — SSOT di core/uom
        **uom_patch,
        "active": True,
        "created_by": user.get("name", ""),
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
    }
    await db.rahaza_materials.insert_one(doc)
    out = _material_to_acc_item(doc, 0.0)
    return JSONResponse(serialize_doc(out), status_code=201)


@router.put("/items/{item_id}")
async def update_item(item_id: str, request: Request):
    await require_auth(request)
    db = get_db()
    body = await request.json()
    existing = await db.rahaza_materials.find_one({"id": item_id, "type": "accessory"})
    if not existing:
        raise HTTPException(404, "Aksesoris tidak ditemukan")

    upd: dict = {}
    allowed = ("name", "category", "description", "supplier", "notes")
    for k in allowed:
        if k in body:
            upd[k] = body[k]
    if "code" in body and body["code"]:
        upd["code"] = str(body["code"]).strip().upper()
    if "unit" in body and body["unit"]:
        upd["unit"] = _normalize_unit(body["unit"])
    if "min_stock" in body:
        try:
            upd["min_stock"] = float(body["min_stock"] or 0)
        except Exception:
            upd["min_stock"] = 0.0
    # FASE G+: harga satuan (unit_cost / alias hpp)
    if "unit_cost" in body or "hpp" in body:
        try:
            upd["unit_cost"] = float(body.get("unit_cost") if body.get("unit_cost") is not None else body.get("hpp") or 0)
        except Exception:
            upd["unit_cost"] = 0.0
    
    # Satuan & kemasan — hanya diproses bila salah satu field satuan dikirim,
    # supaya PATCH parsial (mis. hanya ubah nama) tidak menyentuh `uoms`.
    if any(k in body for k in ("uoms", "unit", "base_uom", "pack_unit", "pack_size",
                               "display_in_packs", "purchase_uom", "issue_uom", "display_uom")):
        try:
            upd.update(uom.apply_payload({**body, **({"unit": upd["unit"]} if "unit" in upd else {})},
                                         existing))
        except uom.UomError as e:
            raise HTTPException(400, f"Satuan tidak valid: {e}")
    if "deleted" in body:
        upd["active"] = not bool(body["deleted"])
    upd["updated_at"] = _now_iso()

    await db.rahaza_materials.update_one({"id": item_id}, {"$set": upd})
    result = await db.rahaza_materials.find_one({"id": item_id}, {"_id": 0})
    qty = await _stock_qty(db, item_id)
    return serialize_doc(_material_to_acc_item(result, qty))


@router.delete("/items/{item_id}")
async def delete_item(item_id: str, request: Request):
    await require_auth(request)
    db = get_db()
    res = await db.rahaza_materials.update_one(
        {"id": item_id, "type": "accessory"},
        {"$set": {"active": False, "updated_at": _now_iso()}},
    )
    if res.matched_count == 0:
        raise HTTPException(404, "Aksesoris tidak ditemukan")
    return {"ok": True}


# ═══════════════════════════════════════════════════════════════
# STOK — receive / issue / movements / overview
# ═══════════════════════════════════════════════════════════════

