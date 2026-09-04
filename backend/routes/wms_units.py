"""
WMS — Unit Master & Conversion Rules
Phase 1: Foundation

Collections:
- wh_unit_master: {id, code, name, category, symbol, is_base, base_unit_id, notes, active}
- wh_unit_conversions: {id, from_unit_id, to_unit_id, factor, formula_expr, notes, active}

Conversion logic:
  converted_qty = source_qty * factor (simple linear)
  OR custom formula_expr for non-linear (e.g. roll → meter depends on roll length per material)

Routes:
  GET    /api/wms/units
  POST   /api/wms/units
  PUT    /api/wms/units/{id}
  DELETE /api/wms/units/{id}
  GET    /api/wms/unit-conversions
  POST   /api/wms/unit-conversions
  PUT    /api/wms/unit-conversions/{id}
  DELETE /api/wms/unit-conversions/{id}
  POST   /api/wms/units/convert  — calculate: {qty, from_unit, to_unit}
  GET    /api/wms/units/all-codes — flat list of codes (for dropdown validation)
"""

import uuid
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from database import get_db
from auth import require_auth, serialize_doc, log_activity

router = APIRouter(prefix="/api/wms", tags=["wms-units"])


def _uid(): return str(uuid.uuid4())
def _now(): return datetime.now(timezone.utc)


# ─── Pre-seeded Unit Categories ───────────────────────────────────────────────
SEED_UNITS = [
    # Panjang
    {"code": "m",     "name": "Meter",      "category": "length",  "symbol": "m",    "is_base": True},
    {"code": "cm",    "name": "Centimeter",  "category": "length",  "symbol": "cm",   "is_base": False},
    {"code": "yard",  "name": "Yard",        "category": "length",  "symbol": "yd",   "is_base": False},
    {"code": "inch",  "name": "Inch",        "category": "length",  "symbol": "in",   "is_base": False},
    # Berat
    {"code": "kg",    "name": "Kilogram",    "category": "weight",  "symbol": "kg",   "is_base": True},
    {"code": "gram",  "name": "Gram",        "category": "weight",  "symbol": "g",    "is_base": False},
    {"code": "ton",   "name": "Ton",         "category": "weight",  "symbol": "ton",  "is_base": False},
    # Satuan hitung
    {"code": "pcs",   "name": "Pieces",      "category": "count",   "symbol": "pcs",  "is_base": True},
    {"code": "lusin", "name": "Lusin (12)",  "category": "count",   "symbol": "lsn",  "is_base": False},
    {"code": "kodi",  "name": "Kodi (20)",   "category": "count",   "symbol": "kdi",  "is_base": False},
    {"code": "gross", "name": "Gross (144)", "category": "count",   "symbol": "grs",  "is_base": False},
    {"code": "helai", "name": "Helai",       "category": "count",   "symbol": "hlai", "is_base": False},
    {"code": "set",   "name": "Set",         "category": "count",   "symbol": "set",  "is_base": False},
    {"code": "pair",  "name": "Pair/Pasang", "category": "count",   "symbol": "pr",   "is_base": False},
    # Gulungan/Kemasan
    {"code": "rol",   "name": "Rol/Gulungan","category": "roll",    "symbol": "rol",  "is_base": True},
    {"code": "gulung","name": "Gulung",      "category": "roll",    "symbol": "glg",  "is_base": False},
    {"code": "bal",   "name": "Bal",         "category": "pack",    "symbol": "bal",  "is_base": True},
    {"code": "karton","name": "Karton",      "category": "pack",    "symbol": "ktn",  "is_base": False},
    {"code": "pak",   "name": "Pak",         "category": "pack",    "symbol": "pak",  "is_base": False},
    {"code": "sak",   "name": "Sak/Kantong", "category": "pack",    "symbol": "sak",  "is_base": False},
    # Volume
    {"code": "liter", "name": "Liter",       "category": "volume",  "symbol": "L",    "is_base": True},
    {"code": "ml",    "name": "Milliliter",  "category": "volume",  "symbol": "mL",   "is_base": False},
]

SEED_CONVERSIONS = [
    # Panjang (base = m)
    {"from": "cm",    "to": "m",    "factor": 0.01,    "notes": "1 cm = 0.01 m"},
    {"from": "yard",  "to": "m",    "factor": 0.9144,  "notes": "1 yard = 0.9144 m"},
    {"from": "inch",  "to": "m",    "factor": 0.0254,  "notes": "1 inch = 0.0254 m"},
    {"from": "m",     "to": "cm",   "factor": 100,     "notes": "1 m = 100 cm"},
    {"from": "m",     "to": "yard", "factor": 1.09361, "notes": "1 m = 1.09361 yard"},
    # Berat (base = kg)
    {"from": "gram",  "to": "kg",   "factor": 0.001,   "notes": "1 gram = 0.001 kg"},
    {"from": "ton",   "to": "kg",   "factor": 1000,    "notes": "1 ton = 1000 kg"},
    {"from": "kg",    "to": "gram", "factor": 1000,    "notes": "1 kg = 1000 gram"},
    # Satuan hitung (base = pcs)
    {"from": "lusin", "to": "pcs",  "factor": 12,      "notes": "1 lusin = 12 pcs"},
    {"from": "kodi",  "to": "pcs",  "factor": 20,      "notes": "1 kodi = 20 pcs"},
    {"from": "gross", "to": "pcs",  "factor": 144,     "notes": "1 gross = 144 pcs"},
    {"from": "pair",  "to": "pcs",  "factor": 2,       "notes": "1 pair = 2 pcs"},
    # Volume (base = liter)
    {"from": "ml",    "to": "liter","factor": 0.001,   "notes": "1 ml = 0.001 L"},
    {"from": "liter", "to": "ml",   "factor": 1000,    "notes": "1 L = 1000 ml"},
]


# ─── Models ───────────────────────────────────────────────────────────────────

class UnitIn(BaseModel):
    code: str = Field(..., min_length=1, max_length=20, description="e.g. kg, m, rol")
    name: str = Field(..., min_length=1, max_length=80)
    category: str = Field(..., description="weight | length | count | roll | pack | volume | other")
    symbol: str = Field(..., max_length=10, description="Short symbol for display")
    is_base: bool = Field(False, description="Is this the base unit for its category?")
    notes: Optional[str] = None


class ConversionIn(BaseModel):
    from_unit_code: str
    to_unit_code: str
    factor: float = Field(..., gt=0, description="Multiplier: result = qty * factor")
    notes: Optional[str] = None


class ConvertCalcIn(BaseModel):
    qty: float = Field(ge=0)
    from_unit: str
    to_unit: str


# ─── Helpers ──────────────────────────────────────────────────────────────────

async def _get_unit_by_code(db, code: str) -> Optional[dict]:
    return await db.wh_unit_master.find_one({"code": code.lower(), "active": True}, {"_id": 0})


# ─── Seed ─────────────────────────────────────────────────────────────────────

async def ensure_unit_master(db=None) -> dict:
    """Pastikan master satuan & aturan konversi selalu ada.

    Dipanggil saat startup backend (pola yang sama dipakai Cutting lewat
    `ensure_cutting_indexes`). Sebelumnya koleksi `wh_unit_master` /
    `wh_unit_conversions` bisa kosong setelah wipe DB sehingga layar
    "Satuan & Konversi" tampil kosong dan kalkulator melempar 404 —
    padahal tombol Seed-nya tidak pernah ditekan siapa pun (BUG-3 audit).

    Idempotent: aman dipanggil berulang.
    """
    db = db if db is not None else get_db()
    created_units = 0
    created_convs = 0
    for u in SEED_UNITS:
        if not await db.wh_unit_master.find_one({"code": u["code"]}):
            await db.wh_unit_master.insert_one({
                "id": _uid(), "code": u["code"], "name": u["name"],
                "category": u["category"], "symbol": u["symbol"],
                "is_base": u["is_base"], "notes": "", "active": True,
                "created_at": _now(),
            })
            created_units += 1
    for c in SEED_CONVERSIONS:
        fu = await db.wh_unit_master.find_one({"code": c["from"]}, {"_id": 0})
        tu = await db.wh_unit_master.find_one({"code": c["to"]}, {"_id": 0})
        if fu and tu and not await db.wh_unit_conversions.find_one(
                {"from_unit_id": fu["id"], "to_unit_id": tu["id"]}):
            await db.wh_unit_conversions.insert_one({
                "id": _uid(), "from_unit_id": fu["id"], "to_unit_id": tu["id"],
                "from_unit_code": fu["code"], "to_unit_code": tu["code"],
                "factor": c["factor"], "notes": c.get("notes", ""), "active": True,
                "created_at": _now(),
            })
            created_convs += 1
    return {"units_created": created_units, "conversions_created": created_convs}


@router.post("/units/seed")
async def seed_units(request: Request):
    """Seed default unit master and conversions. Safe to call multiple times."""
    await require_auth(request)
    db = get_db()
    created_units = 0
    created_convs = 0

    for u in SEED_UNITS:
        if not await db.wh_unit_master.find_one({"code": u["code"]}):
            await db.wh_unit_master.insert_one({
                "id": _uid(), "code": u["code"], "name": u["name"],
                "category": u["category"], "symbol": u["symbol"],
                "is_base": u["is_base"], "notes": "", "active": True,
                "created_at": _now(),
            })
            created_units += 1

    for c in SEED_CONVERSIONS:
        fu = await db.wh_unit_master.find_one({"code": c["from"]}, {"_id": 0})
        tu = await db.wh_unit_master.find_one({"code": c["to"]}, {"_id": 0})
        if fu and tu:
            existing = await db.wh_unit_conversions.find_one({
                "from_unit_id": fu["id"], "to_unit_id": tu["id"]
            })
            if not existing:
                await db.wh_unit_conversions.insert_one({
                    "id": _uid(), "from_unit_id": fu["id"], "to_unit_id": tu["id"],
                    "from_unit_code": fu["code"], "to_unit_code": tu["code"],
                    "factor": c["factor"], "notes": c.get("notes", ""), "active": True,
                    "created_at": _now(),
                })
                created_convs += 1

    return {"message": "Seed selesai", "units_created": created_units, "conversions_created": created_convs}


# ─── Unit CRUD ────────────────────────────────────────────────────────────────

@router.get("/units")
async def list_units(request: Request, category: Optional[str] = None, active: Optional[bool] = None):
    await require_auth(request)
    db = get_db()
    q = {}
    if category:
        q["category"] = category
    if active is not None:
        q["active"] = active
    units = await db.wh_unit_master.find(q, {"_id": 0}).sort("category", 1).to_list(500)
    return serialize_doc(units)


@router.get("/units/all-codes")
async def get_all_unit_codes(request: Request):
    """Return flat list of active unit codes for dropdown validation."""
    await require_auth(request)
    db = get_db()
    units = await db.wh_unit_master.find({"active": True}, {"_id": 0, "code": 1, "name": 1, "symbol": 1, "category": 1}).sort("code", 1).to_list(500)
    return serialize_doc(units)


@router.post("/units")
async def create_unit(data: UnitIn, request: Request):
    user = await require_auth(request)
    db = get_db()
    code = data.code.lower().strip()
    if await db.wh_unit_master.find_one({"code": code}):
        raise HTTPException(400, f"Unit '{code}' sudah ada")
    unit = {
        "id": _uid(), "code": code, "name": data.name, "category": data.category,
        "symbol": data.symbol, "is_base": data.is_base, "notes": data.notes or "",
        "active": True, "created_at": _now(), "created_by": user.get("email", "system"),
    }
    await db.wh_unit_master.insert_one(unit)
    await log_activity(user["id"], user.get("name",""), "create", "wh_unit", f"Unit: {code}")
    return serialize_doc({"message": "Unit ditambahkan", "unit": unit})


@router.put("/units/{unit_id}")
async def update_unit(unit_id: str, data: UnitIn, request: Request):
    await require_auth(request)
    db = get_db()
    unit = await db.wh_unit_master.find_one({"id": unit_id}, {"_id": 0})
    if not unit:
        raise HTTPException(404, "Unit tidak ditemukan")
    await db.wh_unit_master.update_one({"id": unit_id}, {"$set": {
        "name": data.name, "category": data.category, "symbol": data.symbol,
        "is_base": data.is_base, "notes": data.notes or "", "updated_at": _now(),
    }})
    return serialize_doc({"message": "Unit diupdate"})


@router.delete("/units/{unit_id}")
async def delete_unit(unit_id: str, request: Request):
    await require_auth(request)
    db = get_db()
    unit = await db.wh_unit_master.find_one({"id": unit_id}, {"_id": 0})
    if not unit:
        raise HTTPException(404, "Unit tidak ditemukan")
    # Soft delete
    await db.wh_unit_master.update_one({"id": unit_id}, {"$set": {"active": False, "updated_at": _now()}})
    return {"message": "Unit dinonaktifkan"}


# ─── Conversion CRUD ──────────────────────────────────────────────────────────

@router.get("/unit-conversions")
async def list_conversions(request: Request, category: Optional[str] = None):
    await require_auth(request)
    db = get_db()
    convs = await db.wh_unit_conversions.find({"active": True}, {"_id": 0}).sort("from_unit_code", 1).to_list(500)
    if category:
        unit_codes = [u["code"] for u in await db.wh_unit_master.find({"category": category, "active": True}, {"_id": 0}).to_list(500)]
        convs = [c for c in convs if c["from_unit_code"] in unit_codes or c["to_unit_code"] in unit_codes]
    return serialize_doc(convs)


@router.post("/unit-conversions")
async def create_conversion(data: ConversionIn, request: Request):
    user = await require_auth(request)
    db = get_db()
    fu = await _get_unit_by_code(db, data.from_unit_code)
    tu = await _get_unit_by_code(db, data.to_unit_code)
    if not fu:
        raise HTTPException(404, f"Unit '{data.from_unit_code}' tidak ditemukan")
    if not tu:
        raise HTTPException(404, f"Unit '{data.to_unit_code}' tidak ditemukan")
    if await db.wh_unit_conversions.find_one({"from_unit_id": fu["id"], "to_unit_id": tu["id"], "active": True}):
        raise HTTPException(400, f"Konversi {data.from_unit_code}→{data.to_unit_code} sudah ada")
    conv = {
        "id": _uid(), "from_unit_id": fu["id"], "to_unit_id": tu["id"],
        "from_unit_code": fu["code"], "to_unit_code": tu["code"],
        "factor": data.factor, "notes": data.notes or "", "active": True,
        "created_at": _now(), "created_by": user.get("email", "system"),
    }
    await db.wh_unit_conversions.insert_one(conv)
    return serialize_doc({"message": "Konversi ditambahkan", "conversion": conv})


@router.put("/unit-conversions/{conv_id}")
async def update_conversion(conv_id: str, data: ConversionIn, request: Request):
    await require_auth(request)
    db = get_db()
    conv = await db.wh_unit_conversions.find_one({"id": conv_id}, {"_id": 0})
    if not conv:
        raise HTTPException(404, "Konversi tidak ditemukan")
    await db.wh_unit_conversions.update_one({"id": conv_id}, {"$set": {
        "factor": data.factor, "notes": data.notes or "", "updated_at": _now(),
    }})
    return {"message": "Konversi diupdate"}


@router.delete("/unit-conversions/{conv_id}")
async def delete_conversion(conv_id: str, request: Request):
    await require_auth(request)
    db = get_db()
    await db.wh_unit_conversions.update_one({"id": conv_id}, {"$set": {"active": False, "updated_at": _now()}})
    return {"message": "Konversi dihapus"}


# ─── Convert Calculator ───────────────────────────────────────────────────────

async def _resolve_factor(db, fu: dict, tu: dict):
    """Cari faktor konversi fu → tu. Mengembalikan (factor, jalur) atau (None, None).

    Tiga tingkat pencarian (perbaikan BUG-4 & BUG-5 audit 2026-07-27):
      1. aturan LANGSUNG  fu → tu
      2. aturan KEBALIKAN tu → fu  → dipakai 1/factor  (sebelumnya error)
      3. BERANTAI lewat satuan dasar kategori: fu → base → tu
         (sebelumnya `gram → ton` gagal walau gram→kg dan kg→ton ada)
    """
    direct = await db.wh_unit_conversions.find_one(
        {"from_unit_id": fu["id"], "to_unit_id": tu["id"], "active": True}, {"_id": 0})
    if direct:
        return float(direct["factor"]), "langsung"

    inverse = await db.wh_unit_conversions.find_one(
        {"from_unit_id": tu["id"], "to_unit_id": fu["id"], "active": True}, {"_id": 0})
    if inverse and float(inverse.get("factor") or 0) > 0:
        return 1.0 / float(inverse["factor"]), "kebalikan"

    # Berantai lewat satuan dasar — hanya untuk kategori yang sama
    if fu.get("category") and fu.get("category") == tu.get("category"):
        base = await db.wh_unit_master.find_one(
            {"category": fu["category"], "is_base": True, "active": True}, {"_id": 0})
        if base and base["id"] not in (fu["id"], tu["id"]):
            f1, _ = await _resolve_factor(db, fu, base)
            if f1 is not None:
                f2, _ = await _resolve_factor(db, base, tu)
                if f2 is not None:
                    return f1 * f2, f"berantai lewat {base['code']}"
    return None, None


@router.post("/units/convert")
async def convert_qty(data: ConvertCalcIn, request: Request):
    """Hitung konversi kuantitas. Mengembalikan hasil + faktor + jalur yang dipakai."""
    await require_auth(request)
    db = get_db()
    if data.from_unit == data.to_unit:
        return {"from": data.from_unit, "to": data.to_unit, "input": data.qty,
                "result": data.qty, "factor": 1.0, "path": "sama"}
    fu = await _get_unit_by_code(db, data.from_unit)
    tu = await _get_unit_by_code(db, data.to_unit)
    if not fu:
        raise HTTPException(404, f"Unit '{data.from_unit}' tidak ditemukan")
    if not tu:
        raise HTTPException(404, f"Unit '{data.to_unit}' tidak ditemukan")

    factor, path = await _resolve_factor(db, fu, tu)
    if factor is None:
        # Satuan kemasan (pak/rol/bal/karton) memang TIDAK BISA dikonversi secara
        # global karena isinya berbeda tiap barang — arahkan ke konversi per item.
        pack_like = {"pack", "roll"}
        hint = ""
        if fu.get("category") in pack_like or tu.get("category") in pack_like:
            hint = (" Satuan kemasan isinya berbeda tiap barang, jadi tidak bisa "
                    "diatur global — isi 'Satuan & Kemasan' pada master item terkait.")
        raise HTTPException(
            400,
            f"Tidak ada aturan konversi {data.from_unit}→{data.to_unit}.{hint}")
    result = round(data.qty * factor, 6)
    return serialize_doc({"from": data.from_unit, "to": data.to_unit, "input": data.qty,
                          "result": result, "factor": round(factor, 8), "path": path})
