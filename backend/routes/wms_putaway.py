"""wms_putaway — PUT-AWAY KANONIK & SADAR-LOKASI (Fase 3A).

Konsep (dikonfirmasi user):
  * `rahaza_material_stock` = kebenaran TOTAL qty per material (SSOT Fase 2).
  * `wh_positions` (bin) = PETA PENEMPATAN fisik: bin mana isi material apa & berapa.
  * Put-away MEMINDAHKAN stok on-hand yang "belum dirak" → ke bin (gudang→zona→rak→bin).
    Ini penempatan fisik: TIDAK mengubah total on-hand kanonik.
  * unshelved(material) = onhand_kanonik(material) − Σ(wh_positions.qty utk material tsb).
  * 1 bin = 1 material. Bin sudah berisi material lain → ditolak (sarankan bin lain).

Endpoints (prefix /api/wms/putaway):
  GET  /pending    → item yang perlu dirak (unshelved>0), dikelompokkan Bahan/Aksesoris/Produk Jadi.
  GET  /locations  → pohon gudang→zona→rak→bin (+status & isi) untuk pemilihan/scan tujuan.
  POST /place       → tempatkan qty material ke sebuah bin.
  GET  /placements/{material_id} → daftar bin yang saat ini menampung material tsb.
"""
import uuid
import logging
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, HTTPException, Request, Query
from pydantic import BaseModel, Field

from database import get_db
from auth import require_auth, serialize_doc, log_activity
from core import stock_service
from core import uom as _uom  # SSOT konversi satuan (multi-UOM)
from core import bom_uom as _bom_uom  # cakupan lebar: kemasan + global + kain

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/wms/putaway", tags=["wms-putaway"])


def _uid(): return str(uuid.uuid4())
def _now(): return datetime.now(timezone.utc)


# Pemetaan tipe legacy → 3 kategori bisnis (konsisten dgn itemTaxonomy.js & Fase 1).
_CAT_KEY = {
    "yarn": "bahan", "fabric": "bahan", "kain": "bahan", "benang": "bahan", "interlining": "bahan",
    "accessory": "aksesoris", "packaging": "aksesoris",
    "fg": "fg",
}
_CAT_LABEL = {"bahan": "Bahan", "aksesoris": "Aksesoris", "fg": "Produk Jadi"}


def _category_of(mtype: Optional[str]) -> str:
    return _CAT_KEY.get((mtype or "").lower(), "bahan")


class PlaceIn(BaseModel):
    material_id: str
    qty: float = Field(..., gt=0)
    position_id: str = ""
    position_barcode: str = ""
    # Opsional (INV-UOM-2). Bila diisi, `qty` dianggap dalam satuan tersebut dan
    # dikonversi ke satuan dasar sebelum dibandingkan dengan stok belum-dirak.
    # Tanpa field ini perilaku lama tidak berubah sama sekali.
    input_uom: str = ""


async def _placed_map(db) -> dict:
    """Σ qty per material yang SUDAH ditempatkan di bin (wh_positions)."""
    pipe = [
        {"$match": {"material_id": {"$nin": [None, ""]}}},
        {"$group": {"_id": "$material_id", "placed": {"$sum": {"$ifNull": ["$qty", 0]}}}},
    ]
    out = {}
    async for r in db.wh_positions.aggregate(pipe):
        out[r["_id"]] = float(r.get("placed") or 0)
    return out


async def _unshelved_for(db, material_id: str) -> float:
    onhand = await stock_service.get_onhand(material_id, db=db)
    placed_pipe = [
        {"$match": {"material_id": material_id}},
        {"$group": {"_id": None, "placed": {"$sum": {"$ifNull": ["$qty", 0]}}}},
    ]
    placed = 0.0
    async for r in db.wh_positions.aggregate(placed_pipe):
        placed = float(r.get("placed") or 0)
    return round(onhand - placed, 4)


@router.get("/pending")
async def list_pending(request: Request, search: Optional[str] = None):
    """Material dengan stok 'belum dirak' (unshelved>0), dikelompokkan 3 kategori bisnis."""
    await require_auth(request)
    db = get_db()
    onhand = await stock_service.onhand_map(db=db)          # {material_id: qty}
    placed = await _placed_map(db)                          # {material_id: placed}
    ids = [mid for mid, q in onhand.items() if (q - placed.get(mid, 0)) > 0.0001]
    if not ids:
        return {"groups": {"bahan": [], "aksesoris": [], "fg": []},
                "labels": _CAT_LABEL, "total_items": 0}
    mats = await db.rahaza_materials.find({"id": {"$in": ids}}, {"_id": 0}).to_list(5000)
    mat_by_id = {m["id"]: m for m in mats}
    groups = {"bahan": [], "aksesoris": [], "fg": []}
    total = 0
    for mid in ids:
        m = mat_by_id.get(mid)
        if not m:
            continue  # stok tanpa master (orphan) — abaikan di put-away
        if search:
            s = search.lower()
            if s not in (m.get("code", "") or "").lower() and s not in (m.get("name", "") or "").lower():
                continue
        cat = _category_of(m.get("type"))
        oh = float(onhand.get(mid, 0)); pl = float(placed.get(mid, 0))
        groups[cat].append({
            "material_id": mid,
            "code": m.get("code"), "name": m.get("name"),
            "type": m.get("type"), "unit": m.get("unit", "pcs"),
            "category": cat, "category_label": _CAT_LABEL[cat],
            "onhand": round(oh, 4), "placed": round(pl, 4),
            "unshelved": round(oh - pl, 4),
        })
        total += 1
    for cat in groups:
        groups[cat].sort(key=lambda x: (x.get("code") or "", x.get("name") or ""))
    return {"groups": groups, "labels": _CAT_LABEL, "total_items": total}


@router.get("/locations")
async def list_locations(
    request: Request,
    building_id: Optional[str] = None,
    zone_id: Optional[str] = None,
    rack_id: Optional[str] = None,
    only_available: bool = Query(False, description="hanya bin kosong / non-penuh"),
):
    """Pohon gudang→zona→rak→bin + status & isi bin untuk pemilihan/scan tujuan."""
    await require_auth(request)
    db = get_db()
    buildings = await db.wh_buildings.find({"active": True}, {"_id": 0}).sort("code", 1).to_list(500)
    zones = await db.wh_zones.find({"active": True}, {"_id": 0}).sort("code", 1).to_list(1000)
    racks = await db.wh_racks.find({"active": True}, {"_id": 0}).sort("code", 1).to_list(2000)
    b_map = {b["id"]: b for b in buildings}
    z_map = {z["id"]: z for z in zones}
    r_map = {r["id"]: r for r in racks}

    pq = {}
    if building_id: pq["building_id"] = building_id
    if zone_id: pq["zone_id"] = zone_id
    if rack_id: pq["rack_id"] = rack_id
    positions = await db.wh_positions.find(pq, {"_id": 0}).sort([("shelf_no", 1), ("slot_no", 1)]).to_list(5000)
    pos_out = []
    for p in positions:
        b = b_map.get(p.get("building_id")) or {}
        z = z_map.get(p.get("zone_id")) or {}
        r = r_map.get(p.get("rack_id")) or {}
        occupied_qty = float(p.get("qty") or 0)
        is_empty = occupied_qty <= 0 and not p.get("material_id")
        if only_available and not is_empty:
            # bin terisi material lain dianggap tak tersedia utk material berbeda
            pass  # tetap sertakan; frontend yg validasi 1-bin-1-material
        pos_out.append({
            "id": p.get("id"), "barcode": p.get("barcode"), "label": p.get("label"),
            "building_id": p.get("building_id"), "zone_id": p.get("zone_id"), "rack_id": p.get("rack_id"),
            "building_code": b.get("code"), "zone_code": z.get("code"), "rack_code": r.get("code"),
            "full_label": " / ".join([x for x in [b.get("code"), z.get("code"), r.get("code"), p.get("label")] if x]),
            "status": p.get("status", "empty"),
            "material_id": p.get("material_id"), "material_code": p.get("material_code"),
            "material_name": p.get("material_name"), "qty": occupied_qty, "unit": p.get("unit"),
            "is_empty": is_empty,
        })
    return {
        "buildings": [{"id": b["id"], "code": b.get("code"), "name": b.get("name")} for b in buildings],
        "zones": [{"id": z["id"], "building_id": z.get("building_id"), "code": z.get("code"), "name": z.get("name")} for z in zones],
        "racks": [{"id": r["id"], "zone_id": r.get("zone_id"), "building_id": r.get("building_id"), "code": r.get("code"), "name": r.get("name")} for r in racks],
        "positions": pos_out,
    }


@router.get("/placements/{material_id}")
async def list_placements(material_id: str, request: Request):
    """Bin yang saat ini menampung material tsb + ringkas onhand/placed/unshelved."""
    await require_auth(request)
    db = get_db()
    positions = await db.wh_positions.find(
        {"material_id": material_id, "qty": {"$gt": 0}}, {"_id": 0}
    ).to_list(1000)
    onhand = await stock_service.get_onhand(material_id, db=db)
    unshelved = await _unshelved_for(db, material_id)
    return {
        "material_id": material_id,
        "onhand": round(onhand, 4),
        "placed": round(onhand - unshelved, 4),
        "unshelved": round(unshelved, 4),
        "positions": serialize_doc(positions),
    }


@router.post("/place")
async def place(data: PlaceIn, request: Request):
    """Tempatkan qty material ke sebuah bin. Placement fisik → TIDAK ubah total on-hand kanonik.

    2026-08-06 — gerbang izin terpusat (fallback aman): dulu terbuka untuk semua
    user login (`legacy_any=True` mempertahankan itu selama izin role belum
    diatur owner). Begitu izin diatur, butuh `wh.putaway.manage`.
    """
    from routes.shared import require_perm
    user = await require_perm(
        request, "wh.putaway.manage", "warehouse.manage", legacy_any=True,
        message="Akses ditolak: butuh izin put-away gudang (wh.putaway.manage).",
    )
    db = get_db()

    mat = await db.rahaza_materials.find_one({"id": data.material_id}, {"_id": 0})
    if not mat:
        raise HTTPException(404, "Material tidak ditemukan.")

    # Resolve bin (by id atau barcode)
    pos = None
    if data.position_id:
        pos = await db.wh_positions.find_one({"id": data.position_id}, {"_id": 0})
    if not pos and data.position_barcode:
        pos = await db.wh_positions.find_one({"barcode": data.position_barcode}, {"_id": 0})
    if not pos:
        raise HTTPException(404, "Lokasi bin tidak ditemukan (cek id/barcode).")

    # 1 bin = 1 material
    existing_mat = pos.get("material_id")
    if existing_mat and existing_mat != data.material_id and float(pos.get("qty") or 0) > 0:
        raise HTTPException(400, f"Bin {pos.get('barcode')} sudah berisi material lain "
                                 f"({pos.get('material_code') or existing_mat}). Pilih bin kosong lain.")

    # Validasi qty ≤ unshelved
    qty = round(float(data.qty), 4)
    uom_trace = {}
    input_uom = (data.input_uom or "").strip().lower()
    if input_uom and input_uom != _uom.base_uom_of(mat):
        try:
            # cakupan lebar (kemasan material + satuan global + kain) — sama dengan
            # daftar satuan yang ditawarkan layar (GET /rahaza/materials/uom-options)
            factor, source = _bom_uom.factor_to_base(mat, input_uom)
        except _uom.UomError as e:
            raise HTTPException(400, str(e))
        uom_trace = {"input_qty": qty, "input_uom": input_uom, "uom_factor": factor,
                     "uom_source": source}
        qty = round(qty * factor, 4)
    unshelved = await _unshelved_for(db, data.material_id)
    if unshelved <= 0:
        raise HTTPException(400, "Tidak ada stok yang belum dirak untuk material ini.")
    if qty > unshelved + 0.0001:
        raise HTTPException(400, f"Qty melebihi stok belum dirak (tersedia {unshelved} {mat.get('unit','pcs')}).")

    new_qty = round(float(pos.get("qty") or 0) + qty, 4)
    await db.wh_positions.update_one(
        {"id": pos["id"]},
        {"$set": {
            "material_id": data.material_id,
            "material_code": mat.get("code"),
            "material_name": mat.get("name"),
            "unit": mat.get("unit", "pcs"),
            "qty": new_qty,
            "status": "occupied",
            "last_updated": _now(),
        }},
    )

    # Audit penempatan (koleksi terpisah — BUKAN ledger qty kanonik; total tidak berubah).
    await db.wh_placement_movements.insert_one({
        "id": _uid(),
        "type": "putaway",
        "material_id": data.material_id,
        "material_code": mat.get("code"),
        "material_name": mat.get("name"),
        "position_id": pos["id"],
        "position_barcode": pos.get("barcode"),
        "position_label": pos.get("label"),
        "qty": qty,
        "qty_after": new_qty,
        "created_at": _now(),
        "created_by": user.get("email", user.get("name", "system")),
        **uom_trace,
    })

    await log_activity(user.get("id", ""), user.get("name", ""), "putaway", "wh_positions",
                       f"Put-away {qty} {mat.get('code')} → {pos.get('barcode')}")

    remaining = await _unshelved_for(db, data.material_id)
    return {
        "ok": True,
        "position": {"id": pos["id"], "barcode": pos.get("barcode"), "qty": new_qty,
                     "material_code": mat.get("code")},
        "placed_qty": qty,
        "remaining_unshelved": round(remaining, 4),
    }
