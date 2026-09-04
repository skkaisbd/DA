"""
FG Size/Color Matrix Aggregation
=================================

P1-WH-3 — Session 22 (Phase 4)

Provides matrix view of FG (Finished Goods) stock pivoted by Model × Color × Size.

**Strategy:**
- FG materials (`rahaza_materials.type = 'fg'`) are flat SKUs.
- Model/Size/Color attributes are derived from:
  1. Explicit `model_id`/`size_id`/`color` fields (if present)
  2. Parsed from material `code` pattern: `MODEL-COLOR-SIZE` (e.g. `TSHIRT-RED-M`)
  3. Material `name` parsing fallback
- Stock is summed from `rahaza_material_stock` for each material_id.

**Endpoints:**
- GET  /api/rahaza/fg-matrix              → full matrix grouped by model
- GET  /api/rahaza/fg-matrix/models       → list of unique models with stock
- GET  /api/rahaza/fg-matrix/cell-detail  → detail of one matrix cell (variants + stock)
- POST /api/rahaza/fg-matrix/allocate     → reserve qty for an order (status: reserved)
- POST /api/rahaza/fg-matrix/release      → release reservation back to available
"""
from fastapi import APIRouter, Request, HTTPException, Query
from database import get_db
from core.stock_schema import read_qty, read_reserved
from core import stock_service
from utils.counters import gen_prefixed_number
from auth import require_auth, serialize_doc, log_activity
from datetime import datetime, timezone
import uuid
import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/rahaza/fg-matrix", tags=["fg-matrix"])


def _uid(): return str(uuid.uuid4())
def _now(): return datetime.now(timezone.utc)


# ── Parsing Helpers ───────────────────────────────────────────────────────────

# Standard size codes recognized for parsing
STANDARD_SIZES = ["XXS", "XS", "S", "M", "L", "XL", "XXL", "XXXL", "3XL", "4XL", "5XL",
                  "ALLSIZE", "FREESIZE", "ONESIZE"]


def _parse_size_color_from_code(code: str, name: str = "") -> tuple:
    """
    Parse (model_key, color, size) from material code/name.
    
    Tries patterns:
    - CODE: "MODEL-COLOR-SIZE" (e.g., "TSHIRT-RED-M")
    - CODE: "MODEL_COLOR_SIZE"
    - CODE: "MODELCOLORSIZE" (rare, fallback)
    - NAME: "Model Name - Color - Size"
    
    Returns: (model_key, color, size) — all uppercase, '-' if not parseable
    """
    if not code:
        return ('-', '-', '-')
    
    # Normalize separators
    parts = re.split(r'[-_/\s]+', code.upper().strip())
    parts = [p for p in parts if p]
    
    if len(parts) >= 3:
        # Last part is likely size, second-to-last is color, rest is model
        last = parts[-1]
        second_last = parts[-2]
        if last in STANDARD_SIZES:
            size = last
            color = second_last
            model = '-'.join(parts[:-2])
            return (model, color, size)
        elif second_last in STANDARD_SIZES:
            size = second_last
            color = last
            model = '-'.join(parts[:-2])
            return (model, color, size)
    
    if len(parts) == 2:
        # MODEL-SIZE or MODEL-COLOR
        if parts[1] in STANDARD_SIZES:
            return (parts[0], '-', parts[1])
        return (parts[0], parts[1], '-')
    
    # Fall back: whole code is model
    return (code.upper(), '-', '-')


# ── Matrix Aggregation ────────────────────────────────────────────────────────

@router.get("")
async def get_fg_matrix(
    request: Request,
    model: Optional[str] = Query(None, description="Filter by model name/key (case-insensitive)"),
    only_with_stock: bool = Query(False, description="If true, only return materials with qty > 0"),
):
    """
    Returns the FG stock matrix:
    {
      "summary": { "total_models": N, "total_skus": N, "total_qty": N },
      "size_order": ["S", "M", "L", "XL"],   # global size axis (sorted by order_seq)
      "models": [
        {
          "model_key": "TSHIRT",
          "colors": ["BLACK", "WHITE", "RED"],
          "sizes": ["S", "M", "L", "XL"],
          "total_qty": 250,
          "cells": {
            "BLACK": { "S": {"material_id": "...", "code": "...", "qty": 12, "reserved": 0, "available": 12}, "M": {...} },
            "WHITE": { "S": {...}, ... }
          }
        }
      ]
    }
    """
    await require_auth(request)
    db = get_db()
    
    # Fetch all active FG materials
    mats = await db.rahaza_materials.find(
        {"type": "fg", "active": True}, {"_id": 0}
    ).to_list(2000)
    
    # Fetch stock map: material_id -> { qty, reserved }
    # (INV-2/3) reserved kanonik = stock-row reserved_quantity SAJA. Reservasi manual FG kini
    # juga menaikkan reserved_quantity via stock_service → tidak perlu jumlahkan collection lagi.
    stock_rows = await db.rahaza_material_stock.find({}, {"_id": 0}).to_list(5000)
    stock_map = {}
    for s in stock_rows:
        mid = s.get("material_id")
        if not mid:
            continue
        existing = stock_map.get(mid, {"qty": 0, "reserved": 0})
        existing["qty"] += read_qty(s)
        existing["reserved"] += read_reserved(s)
        stock_map[mid] = existing
    
    # Fetch global size order from rahaza_sizes
    sizes_master = await db.rahaza_sizes.find({"active": True}, {"_id": 0}).sort("order_seq", 1).to_list(100)
    size_order = [s["code"] for s in sizes_master]
    # Append common non-master sizes at the end if needed
    for extra in ["ALLSIZE", "FREESIZE", "ONESIZE"]:
        if extra not in size_order:
            size_order.append(extra)
    
    # Group materials by model_key
    grouped = {}  # model_key -> { colors: set, sizes: set, cells: {color: {size: cell_data}} }
    
    for m in mats:
        # Parse model/color/size — prefer explicit fields if present
        explicit_size = (m.get("size_code") or "").upper().strip()
        explicit_color = (m.get("color") or "").upper().strip()
        
        if explicit_size or explicit_color:
            model_key, parsed_color, parsed_size = _parse_size_color_from_code(m.get("code", ""), m.get("name", ""))
            color = explicit_color or parsed_color
            size = explicit_size or parsed_size
        else:
            model_key, color, size = _parse_size_color_from_code(m.get("code", ""), m.get("name", ""))
        
        if not model_key or model_key == '-':
            model_key = m.get("name", "Unknown")[:30]
        
        # Apply filter
        if model and model.upper() not in model_key.upper():
            continue
        
        # Stock
        s = stock_map.get(m["id"], {"qty": 0, "reserved": 0})
        reserved = s["reserved"]
        qty_total = s["qty"]
        available = max(0, qty_total - reserved)
        
        if only_with_stock and qty_total <= 0:
            continue
        
        if model_key not in grouped:
            grouped[model_key] = {
                "model_key": model_key,
                "colors": set(),
                "sizes": set(),
                "cells": {},
                "total_qty": 0,
                "total_available": 0,
            }
        g = grouped[model_key]
        g["colors"].add(color)
        g["sizes"].add(size)
        if color not in g["cells"]:
            g["cells"][color] = {}
        g["cells"][color][size] = {
            "material_id": m["id"],
            "code": m.get("code"),
            "name": m.get("name"),
            "qty": qty_total,
            "reserved": reserved,
            "available": available,
            "unit": m.get("unit", "pcs"),
        }
        g["total_qty"] += qty_total
        g["total_available"] += available
    
    # Convert to JSON-friendly format
    models_out = []
    total_sku = 0
    total_qty = 0
    
    for key in sorted(grouped.keys()):
        g = grouped[key]
        colors_sorted = sorted(g["colors"])
        # Sort sizes by master order_seq when possible
        size_idx = {s: i for i, s in enumerate(size_order)}
        sizes_sorted = sorted(g["sizes"], key=lambda s: size_idx.get(s, 9999))
        
        sku_count = sum(len(g["cells"].get(c, {})) for c in colors_sorted)
        total_sku += sku_count
        total_qty += g["total_qty"]
        
        models_out.append({
            "model_key": g["model_key"],
            "colors": colors_sorted,
            "sizes": sizes_sorted,
            "cells": g["cells"],
            "total_qty": g["total_qty"],
            "total_available": g["total_available"],
            "sku_count": sku_count,
        })
    
    return {
        "summary": {
            "total_models": len(models_out),
            "total_skus": total_sku,
            "total_qty": total_qty,
        },
        "size_order": size_order,
        "models": models_out,
    }


@router.get("/models")
async def get_fg_models(request: Request):
    """Lightweight list of unique FG model keys (for filter dropdown)."""
    await require_auth(request)
    db = get_db()
    mats = await db.rahaza_materials.find({"type": "fg", "active": True}, {"_id": 0, "code": 1, "name": 1}).to_list(2000)
    model_set = set()
    for m in mats:
        model_key, _, _ = _parse_size_color_from_code(m.get("code", ""), m.get("name", ""))
        if model_key and model_key != '-':
            model_set.add(model_key)
    return sorted(model_set)


@router.get("/cell-detail/{material_id}")
async def get_fg_cell_detail(material_id: str, request: Request):
    """
    Detail per cell: material info, stock breakdown per location, recent movements, active reservations.
    """
    await require_auth(request)
    db = get_db()
    
    mat = await db.rahaza_materials.find_one({"id": material_id}, {"_id": 0})
    if not mat:
        raise HTTPException(404, "FG material not found")
    
    # Stock per location
    stocks = await db.rahaza_material_stock.find({"material_id": material_id}, {"_id": 0}).to_list(100)
    
    # Recent movements (last 20)
    movements = await db.rahaza_fg_movements.find(
        {"material_id": material_id}, {"_id": 0}
    ).sort("timestamp", -1).limit(20).to_list(20)
    
    # Active reservations
    reservations = await db.rahaza_fg_reservations.find(
        {"material_id": material_id, "status": "active"}, {"_id": 0}
    ).sort("created_at", -1).to_list(50)
    
    total_qty = sum(read_qty(s) for s in stocks)
    # (INV-2/3) reserved kanonik dari stock-row reserved_quantity (bukan collection reservasi).
    total_reserved = sum(read_reserved(s) for s in stocks)
    
    return {
        "material": serialize_doc(mat),
        "stocks_by_location": serialize_doc(stocks),
        "recent_movements": serialize_doc(movements),
        "active_reservations": serialize_doc(reservations),
        "totals": {
            "qty": total_qty,
            "reserved": total_reserved,
            "available": max(0, total_qty - total_reserved),
        }
    }


# ── Allocation / Reservation ──────────────────────────────────────────────────

@router.post("/allocate")
async def allocate_fg(request: Request):
    """
    Reserve qty of an FG material for an order/customer.
    
    Body: {
      material_id: str,
      qty: int,
      reference_type: str  ("order" | "customer_po" | "manual"),
      reference_id: str?,
      reference_label: str?,  -- shown in UI
      notes: str?,
    }
    """
    user = await require_auth(request)
    db = get_db()
    body = await request.json()
    
    material_id = body.get("material_id")
    qty = float(body.get("qty") or 0)
    ref_type = body.get("reference_type", "manual")
    ref_id = body.get("reference_id")
    ref_label = body.get("reference_label", "")
    notes = body.get("notes", "")
    
    if not material_id:
        raise HTTPException(400, "material_id is required")
    if qty <= 0:
        raise HTTPException(400, "qty must be > 0")
    
    mat = await db.rahaza_materials.find_one({"id": material_id}, {"_id": 0})
    if not mat:
        raise HTTPException(404, "Material not found")
    if mat.get("type") != "fg":
        raise HTTPException(400, "Material is not FG type")
    
    # (INV-2/3) Reserve pada stok KANONIK (reserved_quantity) — SATU sumber reservasi, sama dgn
    # fulfillment. Menghilangkan over-allocation antara FG Matrix vs Fulfillment.
    try:
        await stock_service.reserve_material(
            material_id, qty,
            ref={"source": "fg_matrix_allocate", "reference_type": ref_type, "reference_id": ref_id},
            actor={"id": user["id"], "email": user.get("email", "")},
            db=db,
        )
    except stock_service.InsufficientStock as e:
        raise HTTPException(400, f"Insufficient available stock. Available: {e.available}, requested: {qty}")
    
    # Create reservation (RC-5 fix: atomic race-safe numbering, was count_documents()+1)
    reservation_no = await gen_prefixed_number(
        db, "rahaza_fg_reservations", "reservation_no",
        f"RES-{_now().strftime('%Y%m')}-", 4)
    doc = {
        "id": _uid(),
        "reservation_no": reservation_no,
        "material_id": material_id,
        "fg_code": mat.get("code"),
        "fg_name": mat.get("name"),
        "qty": qty,
        "unit": mat.get("unit", "pcs"),
        "reference_type": ref_type,
        "reference_id": ref_id,
        "reference_label": ref_label,
        "notes": notes,
        "status": "active",
        "created_by": user["id"],
        "created_by_name": user.get("name", ""),
        "created_at": _now(),
        "updated_at": _now(),
    }
    await db.rahaza_fg_reservations.insert_one(doc)
    
    await log_activity(user["id"], user.get("name", ""), "allocate", "rahaza.fg_reservation",
                      f"{reservation_no}: {mat.get('code')} qty={qty}")
    
    return serialize_doc(doc)


@router.post("/release/{reservation_id}")
async def release_fg(reservation_id: str, request: Request):
    """Release an active reservation back to available stock."""
    user = await require_auth(request)
    db = get_db()
    
    res = await db.rahaza_fg_reservations.find_one({"id": reservation_id}, {"_id": 0})
    if not res:
        raise HTTPException(404, "Reservation not found")
    if res.get("status") != "active":
        raise HTTPException(400, f"Cannot release reservation with status: {res.get('status')}")
    
    # (INV-2/3) Lepas reservasi pada stok KANONIK (reserved_quantity) lintas baris.
    #
    # 2026-08-07 — DULU `except Exception: pass` dengan alasan "release harus tetap
    # menandai reservasi released walau stok sudah bergeser". Alasan itu KELIRU,
    # dan akibatnya stok bisa TERKUNCI SELAMANYA:
    #   * "stok sudah bergeser" TIDAK melempar exception. `release_material()`
    #     melepas greedy lintas baris dan hanya mengembalikan `released` yang lebih
    #     kecil — jadi kasus yang dipakai sebagai pembenaran itu tidak pernah
    #     melewati jalur `except` ini sama sekali.
    #   * Yang benar-benar tertangkap di sini HANYA error nyata (DB/logika). Saat
    #     itu terjadi, baris reservasi ditandai "released" TETAPI
    #     `reserved_quantity` pada stok kanonik TETAP. Hasilnya reservasi hantu:
    #     barang ada secara fisik, `available = qty - reserved` tetap terpotong,
    #     dan tidak ada satu pun dokumen yang bisa dipakai untuk melepasnya lagi.
    # Karena ini MENGUBAH ANGKA stok, sekarang gagal keras: reservasi TIDAK
    # ditandai released kalau stoknya belum benar-benar dilepas.
    try:
        rel = await stock_service.release_material(
            res["material_id"], float(res.get("qty") or 0),
            ref={"source": "fg_matrix_release", "reservation_id": reservation_id},
            actor={"id": user["id"], "email": user.get("email", "")},
            db=db,
        )
    except Exception as e:  # noqa: BLE001
        logger.exception(
            "[fg-matrix] GAGAL melepas reservasi stok — reservasi %s TIDAK ditandai "
            "released supaya tidak jadi reservasi hantu. material=%s qty=%s",
            reservation_id, res.get("material_id"), res.get("qty"))
        raise HTTPException(
            500,
            "Gagal melepas reservasi pada stok. Reservasi TIDAK diubah supaya stok "
            f"tidak terkunci tanpa jejak. Laporkan ke admin: {e}")

    # Pelepasan SEBAGIAN bukan error, tetapi wajib meninggalkan jejak: sisa yang
    # tidak terlepas berarti masih ada `reserved_quantity` yang tak bertuan.
    diminta = round(float(res.get("qty") or 0), 4)
    terlepas = round(float((rel or {}).get("released") or 0), 4)
    kurang = round(diminta - terlepas, 4)
    extra = {}
    if kurang > 1e-6:
        logger.warning(
            "[fg-matrix] reservasi %s dilepas SEBAGIAN: diminta %s, terlepas %s "
            "(kurang %s). Sisa reserved pada stok tidak bertuan — perlu dicek.",
            reservation_id, diminta, terlepas, kurang)
        extra = {"release_shortfall": kurang, "release_released": terlepas}

    await db.rahaza_fg_reservations.update_one(
        {"id": reservation_id},
        {"$set": {"status": "released", "released_at": _now(), "released_by": user.get("name", ""),
                  "updated_at": _now(), **extra}}
    )
    
    await log_activity(user["id"], user.get("name", ""), "release", "rahaza.fg_reservation",
                      f"Released {res.get('reservation_no')}")
    
    out = {"status": "released", "reservation_id": reservation_id, "released_qty": terlepas}
    if kurang > 1e-6:
        out["warning"] = (f"Hanya {terlepas} dari {diminta} yang berhasil dilepas dari "
                          f"reservasi stok. Sisa {kurang} perlu diperiksa admin gudang.")
    return out


@router.get("/reservations")
async def list_fg_reservations(
    request: Request,
    status: Optional[str] = Query("active", description="active | released | fulfilled | all"),
    limit: int = Query(100, ge=1, le=500),
):
    """List FG reservations filtered by status."""
    await require_auth(request)
    db = get_db()
    q = {}
    if status and status != "all":
        q["status"] = status
    rows = await db.rahaza_fg_reservations.find(q, {"_id": 0}).sort("created_at", -1).limit(limit).to_list(500)
    return serialize_doc(rows)


@router.post("/seed-demo")
async def seed_demo(request: Request):
    """Admin utility: seed sample FG data for matrix view demo (idempotent)."""
    await require_auth(request)
    from routes.fg_matrix_seed import seed_fg_matrix_demo
    return await seed_fg_matrix_demo()
