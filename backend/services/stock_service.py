"""
stock_service.py — Kalkulasi Stok dan Ketersediaan Material
CV. Dewi Aditya — P1 Service Layer Expansion

Fungsi:
- get_material_availability(db, material_code, warehouse_id) → available_qty
- get_reserved_qty(db, material_code, work_order_id) → reserved_qty
- bulk_availability(db, material_codes, warehouse_id) → dict[code → qty]
- check_stock_sufficient(db, items) → {ok: bool, shortages: list}
"""
from typing import Optional, List
from motor.motor_asyncio import AsyncIOMotorDatabase


async def get_available_qty(
    db: AsyncIOMotorDatabase,
    material_code: str,
    warehouse_id: Optional[str] = None,
) -> float:
    """Hitung qty tersedia untuk satu material."""
    query: dict = {"material_code": material_code}
    if warehouse_id:
        query["warehouse_id"] = warehouse_id

    # Try rahaza_stock_ledger first
    ledger = await db.rahaza_stock_ledger.find(query, {"_id": 0, "qty_balance": 1}).sort("created_at", -1).limit(1).to_list(1)
    if ledger:
        return float(ledger[0].get("qty_balance") or 0)

    # Fallback: rahaza_materials
    mat = await db.rahaza_materials.find_one({"code": material_code}, {"_id": 0, "stock_qty": 1, "current_stock": 1})
    if mat:
        return float(mat.get("current_stock") or mat.get("stock_qty") or 0)

    return 0.0


async def get_reserved_qty(
    db: AsyncIOMotorDatabase,
    material_code: str,
    exclude_work_order_id: Optional[str] = None,
) -> float:
    """Hitung qty yang sudah direservasi untuk material tertentu."""
    query: dict = {"material_code": material_code, "status": "reserved"}
    if exclude_work_order_id:
        query["work_order_id"] = {"$ne": exclude_work_order_id}
    reservations = await db.rahaza_material_reservations.find(query, {"_id": 0, "qty_reserved": 1}).to_list(500)
    return sum(float(r.get("qty_reserved") or 0) for r in reservations)


async def bulk_availability(
    db: AsyncIOMotorDatabase,
    material_codes: List[str],
    warehouse_id: Optional[str] = None,
) -> dict:
    """Batch query: kembalikan {material_code: available_qty} untuk banyak kode sekaligus."""
    result = {}
    # Build query per code
    for code in material_codes:
        result[code] = await get_available_qty(db, code, warehouse_id)
    return result


async def check_stock_sufficient(
    db: AsyncIOMotorDatabase,
    items: List[dict],
) -> dict:
    """
    Cek apakah semua item memiliki stok cukup.
    items: [{material_code, qty_needed, warehouse_id?}]
    Returns: {ok: bool, shortages: [{material_code, available, needed, shortage}]}
    """
    shortages = []
    for item in items:
        code = item.get("material_code") or ""
        needed = float(item.get("qty_needed") or item.get("qty") or 0)
        wh = item.get("warehouse_id")
        available = await get_available_qty(db, code, wh)
        reserved  = await get_reserved_qty(db, code)
        net = available - reserved
        if net < needed - 0.001:
            shortages.append({
                "material_code": code,
                "available": round(net, 3),
                "needed": needed,
                "shortage": round(needed - net, 3),
            })
    return {"ok": len(shortages) == 0, "shortages": shortages}


async def update_stock_ledger(
    db: AsyncIOMotorDatabase,
    material_code: str,
    qty_change: float,
    transaction_type: str,
    ref_id: str,
    ref_type: str,
    performed_by: str,
    warehouse_id: Optional[str] = None,
    notes: str = "",
) -> dict:
    """
    Catat perubahan stok di ledger.
    qty_change: positif = masuk, negatif = keluar.
    Kembalikan ledger entry baru.
    """
    import uuid
    from datetime import datetime, timezone

    # Get last balance
    last = await db.rahaza_stock_ledger.find_one(
        {"material_code": material_code},
        {"_id": 0, "qty_balance": 1},
        sort=[("created_at", -1)]
    )
    prev_balance = float((last or {}).get("qty_balance") or 0)
    new_balance  = prev_balance + qty_change

    entry = {
        "id": str(uuid.uuid4()),
        "material_code": material_code,
        "warehouse_id": warehouse_id,
        "qty_change": qty_change,
        "qty_balance": round(new_balance, 4),
        "transaction_type": transaction_type,  # issue | return | receipt | adjustment
        "ref_id": ref_id,
        "ref_type": ref_type,
        "performed_by": performed_by,
        "notes": notes,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.rahaza_stock_ledger.insert_one(entry)
    # Keep material doc in sync
    await db.rahaza_materials.update_one(
        {"code": material_code},
        {"$set": {"current_stock": round(new_balance, 4), "updated_at": entry["created_at"]}},
    )
    return {k: v for k, v in entry.items() if k != "_id"}
