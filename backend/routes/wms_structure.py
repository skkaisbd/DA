"""
WMS — Warehouse Structure Management
Phase 1: Building → Zone → Rack → Shelf/Position + Barcode

Collections:
- wh_buildings: {id, code, name, address, active}
- wh_zones: {id, building_id, building_code, code, name, zone_type, description, active}
- wh_racks: {id, zone_id, building_id, code, name, num_shelves, slots_per_shelf, capacity_per_slot, unit, barcode_prefix, active}
- wh_positions: {id, rack_id, zone_id, building_id, shelf_no, slot_no, barcode, label, status, material_id, material_code, material_name, qty, unit, last_updated}

Barcode format: {BLDG}-{ZONE}-{RACK}-S{shelf}-P{slot}
e.g.: WH1-A-R01-S2-P3

Routes (all under /api/wms):
  Buildings:  GET/POST/PUT/DELETE /wms/buildings
  Zones:      GET/POST/PUT/DELETE /wms/zones
  Racks:      GET/POST/PUT/DELETE /wms/racks
  Positions:  GET /wms/positions?rack_id=&zone_id=
              GET /wms/positions/{barcode}  — by barcode (for scanner)
              PUT /wms/positions/{position_id}  — update content
  Map:        GET /wms/map/{building_id}  — full visual map data
"""

import uuid
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, HTTPException, Request, Query
from pydantic import BaseModel, Field
from database import get_db
from auth import require_auth, serialize_doc, log_activity, check_role

router = APIRouter(prefix="/api/wms", tags=["wms-structure"])


def _uid(): return str(uuid.uuid4())
def _now(): return datetime.now(timezone.utc)


# ─── Models ───────────────────────────────────────────────────────────────────

class BuildingIn(BaseModel):
    code: str = Field(..., min_length=1, max_length=20)
    name: str = Field(..., min_length=1)
    address: Optional[str] = None
    description: Optional[str] = None


class ZoneIn(BaseModel):
    building_id: str
    code: str = Field(..., min_length=1, max_length=20)
    name: str = Field(..., min_length=1)
    zone_type: str = Field("general", description="rm | fg | wip | general | transit")
    description: Optional[str] = None


class RackIn(BaseModel):
    zone_id: str
    code: str = Field(..., min_length=1, max_length=20)
    name: str = Field(..., min_length=1)
    num_shelves: int = Field(4, ge=1, le=50, description="Jumlah shelves dalam rak")
    slots_per_shelf: int = Field(5, ge=1, le=100, description="Jumlah slot per shelf")
    capacity_per_slot: float = Field(0, ge=0, description="Kapasitas per slot (0 = unlimited)")
    capacity_unit: Optional[str] = Field(None, description="Satuan kapasitas (kg, pcs, dll)")
    description: Optional[str] = None


class PositionUpdateIn(BaseModel):
    material_id: Optional[str] = None
    material_code: Optional[str] = None
    material_name: Optional[str] = None
    qty: float = Field(default=0, ge=0)
    unit: Optional[str] = None
    notes: Optional[str] = None


# ══════════════════════════════════════════════════════════════════════════════
# BUILDINGS
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/buildings")
async def list_buildings(request: Request):
    await require_auth(request)
    db = get_db()
    buildings = await db.wh_buildings.find({"active": True}, {"_id": 0}).sort("code", 1).to_list(500)
    # Enrich with zone + rack counts
    for b in buildings:
        b["zone_count"] = await db.wh_zones.count_documents({"building_id": b["id"], "active": True})
        b["rack_count"] = await db.wh_racks.count_documents({"building_id": b["id"], "active": True})
    return serialize_doc(buildings)


@router.post("/buildings")
async def create_building(data: BuildingIn, request: Request):
    user = await require_auth(request)
    db = get_db()
    code = data.code.upper().strip()
    if await db.wh_buildings.find_one({"code": code}):
        raise HTTPException(400, f"Kode gedung '{code}' sudah ada")
    building = {
        "id": _uid(), "code": code, "name": data.name,
        "address": data.address or "", "description": data.description or "",
        "active": True, "created_at": _now(), "created_by": user.get("email", "system"),
    }
    await db.wh_buildings.insert_one(building)
    await log_activity(user["id"], user.get("name",""), "create", "wh_building", f"Building: {code}")
    return serialize_doc({"message": "Gedung ditambahkan", "building": building})


@router.put("/buildings/{building_id}")
async def update_building(building_id: str, data: BuildingIn, request: Request):
    await require_auth(request)
    db = get_db()
    bldg = await db.wh_buildings.find_one({"id": building_id})
    if not bldg:
        raise HTTPException(404, "Gedung tidak ditemukan")
    await db.wh_buildings.update_one({"id": building_id}, {"$set": {
        "name": data.name, "address": data.address or "", "description": data.description or "",
        "updated_at": _now(),
    }})
    return {"message": "Gedung diupdate"}


@router.delete("/buildings/{building_id}")
async def delete_building(building_id: str, request: Request):
    await require_auth(request)
    db = get_db()
    rack_count = await db.wh_racks.count_documents({"building_id": building_id, "active": True})
    if rack_count > 0:
        raise HTTPException(400, f"Gedung masih memiliki {rack_count} rak aktif. Hapus/nonaktifkan rak dulu.")
    await db.wh_buildings.update_one({"id": building_id}, {"$set": {"active": False, "updated_at": _now()}})
    return {"message": "Gedung dinonaktifkan"}


# ══════════════════════════════════════════════════════════════════════════════
# ZONES
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/zones")
async def list_zones(request: Request, building_id: Optional[str] = None):
    await require_auth(request)
    db = get_db()
    q = {"active": True}
    if building_id:
        q["building_id"] = building_id
    zones = await db.wh_zones.find(q, {"_id": 0}).sort("code", 1).to_list(500)
    for z in zones:
        z["rack_count"] = await db.wh_racks.count_documents({"zone_id": z["id"], "active": True})
    return serialize_doc(zones)


@router.post("/zones")
async def create_zone(data: ZoneIn, request: Request):
    user = await require_auth(request)
    db = get_db()
    building = await db.wh_buildings.find_one({"id": data.building_id, "active": True}, {"_id": 0})
    if not building:
        raise HTTPException(404, "Gedung tidak ditemukan")
    code = data.code.upper().strip()
    if await db.wh_zones.find_one({"building_id": data.building_id, "code": code}):
        raise HTTPException(400, f"Kode zona '{code}' sudah ada di gedung ini")
    zone = {
        "id": _uid(), "building_id": data.building_id, "building_code": building["code"],
        "building_name": building["name"], "code": code, "name": data.name,
        "zone_type": data.zone_type, "description": data.description or "",
        "active": True, "created_at": _now(), "created_by": user.get("email", "system"),
    }
    await db.wh_zones.insert_one(zone)
    await log_activity(user["id"], user.get("name",""), "create", "wh_zone", f"Zone: {building['code']}-{code}")
    return serialize_doc({"message": "Zona ditambahkan", "zone": zone})


@router.put("/zones/{zone_id}")
async def update_zone(zone_id: str, data: ZoneIn, request: Request):
    await require_auth(request)
    db = get_db()
    zone = await db.wh_zones.find_one({"id": zone_id})
    if not zone:
        raise HTTPException(404, "Zona tidak ditemukan")
    await db.wh_zones.update_one({"id": zone_id}, {"$set": {
        "name": data.name, "zone_type": data.zone_type, "description": data.description or "",
        "updated_at": _now(),
    }})
    return {"message": "Zona diupdate"}


@router.delete("/zones/{zone_id}")
async def delete_zone(zone_id: str, request: Request):
    await require_auth(request)
    db = get_db()
    rack_count = await db.wh_racks.count_documents({"zone_id": zone_id, "active": True})
    if rack_count > 0:
        raise HTTPException(400, f"Zona masih memiliki {rack_count} rak. Hapus/nonaktifkan rak dulu.")
    await db.wh_zones.update_one({"id": zone_id}, {"$set": {"active": False, "updated_at": _now()}})
    return {"message": "Zona dinonaktifkan"}


# ══════════════════════════════════════════════════════════════════════════════
# RACKS
# ══════════════════════════════════════════════════════════════════════════════

async def _generate_positions(db, rack: dict):
    """Auto-generate position slots for a rack based on num_shelves × slots_per_shelf."""
    num_shelves = rack["num_shelves"]
    slots_per_shelf = rack["slots_per_shelf"]
    bldg_code = rack.get("building_code", "WH")
    zone_code = rack.get("zone_code", "Z")
    rack_code = rack["code"]

    positions = []
    for shelf in range(1, num_shelves + 1):
        for slot in range(1, slots_per_shelf + 1):
            barcode = f"{bldg_code}-{zone_code}-{rack_code}-S{shelf:02d}-P{slot:02d}"
            label = f"Shelf {shelf}, Slot {slot}"
            pos = {
                "id": _uid(),
                "rack_id": rack["id"],
                "zone_id": rack["zone_id"],
                "building_id": rack["building_id"],
                "building_code": bldg_code,
                "zone_code": zone_code,
                "rack_code": rack_code,
                "shelf_no": shelf,
                "slot_no": slot,
                "barcode": barcode,
                "label": label,
                "status": "empty",  # empty | occupied | reserved
                "material_id": None,
                "material_code": None,
                "material_name": None,
                "qty": 0,
                "unit": None,
                "lot_number": None,
                "notes": "",
                "last_updated": _now(),
            }
            positions.append(pos)
    if positions:
        await db.wh_positions.insert_many(positions)
    return len(positions)


@router.get("/racks")
async def list_racks(request: Request, zone_id: Optional[str] = None, building_id: Optional[str] = None):
    await require_auth(request)
    db = get_db()
    q = {"active": True}
    if zone_id:
        q["zone_id"] = zone_id
    if building_id:
        q["building_id"] = building_id
    racks = await db.wh_racks.find(q, {"_id": 0}).sort("code", 1).to_list(500)
    for r in racks:
        total = r["num_shelves"] * r["slots_per_shelf"]
        occupied = await db.wh_positions.count_documents({"rack_id": r["id"], "status": "occupied"})
        r["total_positions"] = total
        r["occupied_positions"] = occupied
        r["empty_positions"] = total - occupied
        r["occupancy_pct"] = round(occupied / total * 100) if total else 0
    return serialize_doc(racks)


@router.post("/racks")
async def create_rack(data: RackIn, request: Request):
    user = await require_auth(request)
    db = get_db()
    zone = await db.wh_zones.find_one({"id": data.zone_id, "active": True}, {"_id": 0})
    if not zone:
        raise HTTPException(404, "Zona tidak ditemukan")
    building = await db.wh_buildings.find_one({"id": zone["building_id"], "active": True}, {"_id": 0})
    if not building:
        raise HTTPException(404, "Gedung tidak ditemukan")

    code = data.code.upper().strip()
    if await db.wh_racks.find_one({"zone_id": data.zone_id, "code": code}):
        raise HTTPException(400, f"Kode rak '{code}' sudah ada di zona ini")

    rack = {
        "id": _uid(),
        "zone_id": data.zone_id,
        "zone_code": zone["code"],
        "zone_name": zone["name"],
        "building_id": zone["building_id"],
        "building_code": building["code"],
        "building_name": building["name"],
        "code": code,
        "name": data.name,
        "num_shelves": data.num_shelves,
        "slots_per_shelf": data.slots_per_shelf,
        "capacity_per_slot": data.capacity_per_slot,
        "capacity_unit": data.capacity_unit or "",
        "description": data.description or "",
        "active": True,
        "created_at": _now(),
        "created_by": user.get("email", "system"),
    }

    await db.wh_racks.insert_one(rack)

    # Auto-generate positions
    pos_count = await _generate_positions(db, rack)

    await log_activity(user["id"], user.get("name",""), "create", "wh_rack",
                       f"Rack {building['code']}-{zone['code']}-{code} ({pos_count} positions)")

    return serialize_doc({
        "message": f"Rak ditambahkan dengan {pos_count} posisi",
        "rack": rack,
        "positions_created": pos_count,
    })


@router.put("/racks/{rack_id}")
async def update_rack(rack_id: str, data: RackIn, request: Request):
    await require_auth(request)
    db = get_db()
    rack = await db.wh_racks.find_one({"id": rack_id}, {"_id": 0})
    if not rack:
        raise HTTPException(404, "Rak tidak ditemukan")

    old_shelves = rack["num_shelves"]
    old_slots = rack["slots_per_shelf"]
    new_shelves = data.num_shelves
    new_slots = data.slots_per_shelf
    structure_changed = (old_shelves != new_shelves) or (old_slots != new_slots)

    await db.wh_racks.update_one({"id": rack_id}, {"$set": {
        "name": data.name, "num_shelves": new_shelves,
        "slots_per_shelf": new_slots,
        "capacity_per_slot": data.capacity_per_slot,
        "capacity_unit": data.capacity_unit or "",
        "description": data.description or "", "updated_at": _now(),
    }})

    added = 0
    if structure_changed:
        # Only add new positions (don't remove existing to preserve stock data)
        # For new shelves/slots that don't exist yet, add them
        existing_positions = {(p["shelf_no"], p["slot_no"]) for p in
                              await db.wh_positions.find({"rack_id": rack_id}, {"_id": 0, "shelf_no": 1, "slot_no": 1}).to_list(500)}
        updated_rack = await db.wh_racks.find_one({"id": rack_id}, {"_id": 0})
        bldg_code = updated_rack.get("building_code", "WH")
        zone_code = updated_rack.get("zone_code", "Z")
        new_positions = []
        for shelf in range(1, new_shelves + 1):
            for slot in range(1, new_slots + 1):
                if (shelf, slot) not in existing_positions:
                    barcode = f"{bldg_code}-{zone_code}-{updated_rack['code']}-S{shelf:02d}-P{slot:02d}"
                    new_positions.append({
                        "id": _uid(), "rack_id": rack_id,
                        "zone_id": updated_rack["zone_id"], "building_id": updated_rack["building_id"],
                        "building_code": bldg_code, "zone_code": zone_code, "rack_code": updated_rack["code"],
                        "shelf_no": shelf, "slot_no": slot, "barcode": barcode,
                        "label": f"Shelf {shelf}, Slot {slot}", "status": "empty",
                        "material_id": None, "material_code": None, "material_name": None,
                        "qty": 0, "unit": None, "lot_number": None, "notes": "",
                        "last_updated": _now(),
                    })
        if new_positions:
            await db.wh_positions.insert_many(new_positions)
            added = len(new_positions)

    return serialize_doc({"message": f"Rak diupdate{f', {added} posisi baru ditambahkan' if added else ''}"})


@router.delete("/racks/{rack_id}")
async def delete_rack(rack_id: str, request: Request):
    await require_auth(request)
    db = get_db()
    occupied = await db.wh_positions.count_documents({"rack_id": rack_id, "status": "occupied"})
    if occupied > 0:
        raise HTTPException(400, f"Rak masih memiliki {occupied} posisi terisi. Pindahkan barang dulu.")
    await db.wh_racks.update_one({"id": rack_id}, {"$set": {"active": False, "updated_at": _now()}})
    return {"message": "Rak dinonaktifkan"}


# ══════════════════════════════════════════════════════════════════════════════
# POSITIONS
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/positions")
async def list_positions(
    request: Request,
    rack_id: Optional[str] = None,
    zone_id: Optional[str] = None,
    building_id: Optional[str] = None,
    status: Optional[str] = None,
    material_id: Optional[str] = None,
):
    await require_auth(request)
    db = get_db()
    q = {}
    if rack_id:
        q["rack_id"] = rack_id
    if zone_id:
        q["zone_id"] = zone_id
    if building_id:
        q["building_id"] = building_id
    if status:
        q["status"] = status
    if material_id:
        q["material_id"] = material_id
    positions = await db.wh_positions.find(q, {"_id": 0}).sort([("shelf_no", 1), ("slot_no", 1)]).to_list(500)
    return serialize_doc(positions)


@router.get("/positions/by-barcode/{barcode}")
async def get_position_by_barcode(barcode: str, request: Request):
    """Scan barcode → get full position info (for scanner search)."""
    await require_auth(request)
    db = get_db()
    pos = await db.wh_positions.find_one({"barcode": barcode}, {"_id": 0})
    if not pos:
        raise HTTPException(404, f"Posisi dengan barcode '{barcode}' tidak ditemukan")
    return serialize_doc(pos)


@router.put("/positions/{position_id}")
async def update_position(position_id: str, data: PositionUpdateIn, request: Request):
    """Manually update position content (admin correction)."""
    user = await require_auth(request)
    db = get_db()
    pos = await db.wh_positions.find_one({"id": position_id})
    if not pos:
        raise HTTPException(404, "Posisi tidak ditemukan")
    status = "occupied" if (data.material_id and data.qty > 0) else "empty"
    await db.wh_positions.update_one({"id": position_id}, {"$set": {
        "material_id": data.material_id, "material_code": data.material_code,
        "material_name": data.material_name, "qty": data.qty, "unit": data.unit,
        "notes": data.notes or "", "status": status, "last_updated": _now(),
        "updated_by": user.get("email", "system"),
    }})
    return {"message": "Posisi diupdate"}


# ══════════════════════════════════════════════════════════════════════════════
# WAREHOUSE MAP
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/map/{building_id}")
async def get_warehouse_map(building_id: str, request: Request):
    """
    Returns full warehouse map data for interactive dashboard.
    Structure: building → zones → racks → positions (summarized)
    """
    await require_auth(request)
    db = get_db()

    building = await db.wh_buildings.find_one({"id": building_id, "active": True}, {"_id": 0})
    if not building:
        raise HTTPException(404, "Gedung tidak ditemukan")

    zones = await db.wh_zones.find({"building_id": building_id, "active": True}, {"_id": 0}).sort("code", 1).to_list(500)

    for zone in zones:
        racks = await db.wh_racks.find({"zone_id": zone["id"], "active": True}, {"_id": 0}).sort("code", 1).to_list(500)
        for rack in racks:
            total = rack["num_shelves"] * rack["slots_per_shelf"]
            occupied = await db.wh_positions.count_documents({"rack_id": rack["id"], "status": "occupied"})
            reserved = await db.wh_positions.count_documents({"rack_id": rack["id"], "status": "reserved"})
            empty = total - occupied - reserved
            rack["total"] = total
            rack["occupied"] = occupied
            rack["reserved"] = reserved
            rack["empty"] = empty
            rack["occupancy_pct"] = round(occupied / total * 100) if total else 0
            # Color coding
            pct = rack["occupancy_pct"]
            rack["color"] = "red" if pct >= 90 else "orange" if pct >= 70 else "green" if pct < 30 else "yellow"

            # Top materials in this rack
            top_mats = await db.wh_positions.aggregate([
                {"$match": {"rack_id": rack["id"], "status": "occupied", "material_id": {"$ne": None}}},
                {"$group": {"_id": "$material_code", "name": {"$first": "$material_name"}, "total_qty": {"$sum": "$qty"}, "unit": {"$first": "$unit"}}},
                {"$sort": {"total_qty": -1}}, {"$limit": 3}
            ]).to_list(500)
            rack["top_materials"] = [{"code": t["_id"], "name": t["name"], "qty": t["total_qty"], "unit": t["unit"]} for t in top_mats]

        zone["racks"] = racks
        zone["rack_count"] = len(racks)
        zone_total = sum(r["total"] for r in racks)
        zone_occupied = sum(r["occupied"] for r in racks)
        zone["total_positions"] = zone_total
        zone["occupied_positions"] = zone_occupied
        zone["occupancy_pct"] = round(zone_occupied / zone_total * 100) if zone_total else 0

    building["zones"] = zones
    return serialize_doc(building)


# ══════════════════════════════════════════════════════════════════════════════
# SMART SEARCH by SCANNER / BARCODE
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/search")
async def warehouse_search(
    request: Request,
    q: Optional[str] = Query(None, description="Scan barcode or type material code/name"),
    building_id: Optional[str] = None,
):
    """
    Smart search: scan item barcode OR type material code/name.
    Returns all positions where this item is stored.
    """
    await require_auth(request)
    db = get_db()

    if not q or not q.strip():
        return {"positions": [], "materials": []}

    query_str = q.strip()

    # 1. Try barcode match (position barcode or material barcode)
    pos_by_barcode = await db.wh_positions.find_one({"barcode": query_str}, {"_id": 0})
    if pos_by_barcode:
        return serialize_doc({"type": "position", "result": pos_by_barcode})

    # 2. Try material code exact match
    mat_q = {"$or": [
        {"code": {"$regex": f"^{query_str}$", "$options": "i"}},
        {"name": {"$regex": query_str, "$options": "i"}},
    ]}
    if not any(c in query_str for c in [" ", "-"]):
        mat_q = {"$or": [
            {"code": {"$regex": query_str, "$options": "i"}},
            {"name": {"$regex": query_str, "$options": "i"}},
        ]}

    materials = await db.rahaza_materials.find(mat_q, {"_id": 0}).limit(5).to_list(500)
    mat_ids = [m["id"] for m in materials]

    pos_q = {"material_id": {"$in": mat_ids}, "status": "occupied"}
    if building_id:
        pos_q["building_id"] = building_id
    positions = await db.wh_positions.find(pos_q, {"_id": 0}).sort("qty", -1).to_list(500)

    return serialize_doc({
        "type": "material",
        "materials": materials,
        "positions": positions,
        "total_qty": sum(p.get("qty", 0) for p in positions),
    })


# ══════════════════════════════════════════════════════════════════════════════
# OCCUPANCY ALERTS — Rak yang penuh (>= threshold)
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/alerts/occupancy")
async def occupancy_alerts(
    request: Request,
    threshold: int = Query(90, ge=0, le=100, description="Minimum occupancy percentage to flag"),
    building_id: Optional[str] = None,
):
    """
    Mengembalikan daftar rak yang occupancy-nya >= threshold% (default 90%).
    Berguna untuk banner alert di dashboard gudang.
    """
    await require_auth(request)
    db = get_db()
    rack_q = {"active": True}
    if building_id:
        rack_q["building_id"] = building_id
    racks = await db.wh_racks.find(rack_q, {"_id": 0}).to_list(500)

    critical = []
    warning = []
    for r in racks:
        total = (r.get("num_shelves") or 0) * (r.get("slots_per_shelf") or 0)
        if total <= 0:
            continue
        occupied = await db.wh_positions.count_documents({"rack_id": r["id"], "status": "occupied"})
        pct = round(occupied / total * 100) if total else 0
        if pct < threshold:
            continue
        item = {
            "rack_id": r["id"], "rack_code": r.get("code"), "rack_name": r.get("name"),
            "zone_id": r.get("zone_id"), "zone_code": r.get("zone_code"),
            "building_id": r.get("building_id"), "building_code": r.get("building_code"),
            "occupied": occupied, "total": total, "occupancy_pct": pct,
            "free_slots": total - occupied,
            "severity": "critical" if pct >= 95 else "warning",
        }
        if pct >= 95:
            critical.append(item)
        else:
            warning.append(item)
    # Sort by pct desc
    critical.sort(key=lambda x: -x["occupancy_pct"])
    warning.sort(key=lambda x: -x["occupancy_pct"])

    return serialize_doc({
        "threshold": threshold,
        "building_id": building_id,
        "critical_count": len(critical),
        "warning_count": len(warning),
        "total_alerts": len(critical) + len(warning),
        "critical": critical,
        "warning": warning,
    })


# ══════════════════════════════════════════════════════════════════════════════
# FASE B — STRUKTUR STORAGE KANONIK + PETA MIGRASI LOKASI (wh_location_migration_map)
# ══════════════════════════════════════════════════════════════════════════════
# 4 zona storage kanonik di GD-01 + pemetaan dari rahaza_locations (STORAGE saja).
# Zona PRODUKSI (GED-A/B, ZNA-CUTTING/SEWING/QC/PACKING) SENGAJA TIDAK dipetakan —
# tetap milik model produksi/HR (rahaza_locations), tidak dikonflasikan ke wh_*.
CANONICAL_STORAGE_ZONES = [
    {  # reuse zona RM generik lama (ZN-01) bila ada, agar tak muncul zona "duplikat"
        "role": "bahan", "rahaza_codes": ["ZNA-KAIN"],
        "reuse_codes": ["ZN-01", "ZN-KAIN"],
        "code": "ZN-KAIN", "name": "Zona Bahan / Kain", "zone_type": "rm",
    },
    {
        "role": "aksesoris", "rahaza_codes": ["ZNA-AKSESORIS"],
        "reuse_codes": ["ZN-AKS", "ZN-AKSESORIS"],
        "code": "ZN-AKS", "name": "Zona Aksesoris", "zone_type": "general",
    },
    {
        "role": "fg", "rahaza_codes": ["ZNA-FG"],
        "reuse_codes": ["ZN-FG"],
        "code": "ZN-FG", "name": "Zona Produk Jadi", "zone_type": "fg",
    },
    {
        "role": "sample", "rahaza_codes": ["ZNA-SAMPLE"],
        "reuse_codes": ["ZN-SAMPLE", "ZN-SMP"],
        "code": "ZN-SAMPLE", "name": "Zona Sample / RnD", "zone_type": "general",
    },
]


async def _ensure_zone(db, building, spec, user):
    """Idempotent: reuse zona lama (reuse_codes) bila ada; jika tidak, buat baru."""
    for rc in spec["reuse_codes"]:
        z = await db.wh_zones.find_one({"building_id": building["id"], "code": rc, "active": True}, {"_id": 0})
        if z:
            return z, False
    zone = {
        "id": _uid(), "building_id": building["id"], "building_code": building["code"],
        "building_name": building["name"], "code": spec["code"], "name": spec["name"],
        "zone_type": spec["zone_type"], "description": "Zona storage kanonik (Fase B).",
        "active": True, "created_at": _now(), "created_by": user.get("email", "system"),
    }
    await db.wh_zones.insert_one(zone)
    return zone, True


async def _ensure_starter_rack(db, zone, user):
    """Pastikan zona punya minimal 1 rak aktif. Jika belum ada, buat RK-01 (4x6=24 bin)."""
    if await db.wh_racks.count_documents({"zone_id": zone["id"], "active": True}) > 0:
        return None, 0
    building = await db.wh_buildings.find_one({"id": zone["building_id"]}, {"_id": 0})
    rack = {
        "id": _uid(), "zone_id": zone["id"], "zone_code": zone["code"], "zone_name": zone["name"],
        "building_id": zone["building_id"], "building_code": building["code"], "building_name": building["name"],
        "code": "RK-01", "name": "Rak Utama", "num_shelves": 4, "slots_per_shelf": 6,
        "capacity_per_slot": 50.0, "capacity_unit": "pcs", "description": "",
        "active": True, "created_at": _now(), "created_by": user.get("email", "system"),
    }
    await db.wh_racks.insert_one(rack)
    n = await _generate_positions(db, rack)
    return rack, n


@router.post("/structure/build-canonical-storage")
async def build_canonical_storage(request: Request):
    """
    FASE B (idempotent): pastikan 4 zona storage kanonik ada di GD-01 + starter rack,
    lalu bangun/refresh `wh_location_migration_map` (rahaza storage location → wh zone).
    Aman diulang; tidak menghapus/menimpa penempatan fisik yang sudah ada.
    """
    user = await require_auth(request)
    if not check_role(user, ["admin"]):
        raise HTTPException(403, "Hanya admin/superadmin yang boleh membangun struktur gudang.")
    db = get_db()

    building = await db.wh_buildings.find_one({"code": "GD-01", "active": True}, {"_id": 0}) \
        or await db.wh_buildings.find_one({"active": True}, {"_id": 0})
    if not building:
        raise HTTPException(404, "Tidak ada gedung WMS aktif. Buat gedung dulu.")

    result = {"building": building["code"], "zones_created": 0, "zones_reused": 0,
              "racks_created": 0, "positions_created": 0, "map_entries": 0, "zones": [], "map": []}

    for spec in CANONICAL_STORAGE_ZONES:
        zone, created = await _ensure_zone(db, building, spec, user)
        result["zones_created" if created else "zones_reused"] += 1
        rack, npos = await _ensure_starter_rack(db, zone, user)
        if rack:
            result["racks_created"] += 1
            result["positions_created"] += npos
        result["zones"].append({
            "role": spec["role"], "code": zone["code"], "name": zone["name"], "id": zone["id"],
            "created": created, "starter_rack": rack["code"] if rack else None,
        })
        for rcode in spec["rahaza_codes"]:
            loc = await db.rahaza_locations.find_one({"code": rcode}, {"_id": 0})
            entry = {
                "rahaza_location_id": loc["id"] if loc else None,
                "rahaza_code": rcode, "rahaza_name": (loc or {}).get("name"),
                "wh_building_id": building["id"], "wh_building_code": building["code"],
                "wh_zone_id": zone["id"], "wh_zone_code": zone["code"], "wh_zone_name": zone["name"],
                "role": spec["role"], "active": True, "updated_at": _now(),
            }
            await db.wh_location_migration_map.update_one(
                {"rahaza_code": rcode},
                {"$set": entry, "$setOnInsert": {"id": _uid(), "created_at": _now()}},
                upsert=True,
            )
            result["map_entries"] += 1
            result["map"].append({"rahaza_code": rcode, "wh_zone_code": zone["code"],
                                   "role": spec["role"], "rahaza_resolved": bool(loc)})

    await log_activity(user["id"], user.get("name", ""), "build", "wh_structure",
                       f"Canonical storage: +{result['zones_created']} zona, map {result['map_entries']}")
    return serialize_doc({"message": "Struktur storage kanonik & peta migrasi siap.", **result})


@router.get("/structure/location-map")
async def get_location_map(request: Request):
    """Peta migrasi lokasi (rahaza storage → wh zone) untuk Fase C & audit."""
    await require_auth(request)
    db = get_db()
    rows = await db.wh_location_migration_map.find({"active": True}, {"_id": 0}).sort("rahaza_code", 1).to_list(500)
    return serialize_doc(rows)



# ══════════════════════════════════════════════════════════════════════════════
# SEED DEMO STRUCTURE
# ══════════════════════════════════════════════════════════════════════════════

@router.post("/structure/seed-demo")
async def seed_demo_structure(request: Request):
    """Seed 1 building with 2 zones (RM + FG) and sample racks."""
    await require_auth(request)
    db = get_db()
    created = {"buildings": 0, "zones": 0, "racks": 0, "positions": 0}

    # Building
    if not await db.wh_buildings.find_one({"code": "WH1"}):
        bldg = {
            "id": _uid(), "code": "WH1", "name": "Gudang Utama",
            "address": "Jl. Industri No. 1", "description": "Gudang utama bahan baku dan barang jadi",
            "active": True, "created_at": _now(), "created_by": "seed",
        }
        await db.wh_buildings.insert_one(bldg)
        created["buildings"] += 1

        bldg_doc = bldg
    else:
        bldg_doc = await db.wh_buildings.find_one({"code": "WH1"}, {"_id": 0})

    # Zones
    zone_defs = [
        {"code": "RM", "name": "Zona Bahan Baku", "zone_type": "rm"},
        {"code": "FG", "name": "Zona Barang Jadi", "zone_type": "fg"},
        {"code": "WIP", "name": "Zona Work-in-Progress", "zone_type": "wip"},
    ]
    zone_docs = {}
    for zd in zone_defs:
        if not await db.wh_zones.find_one({"building_id": bldg_doc["id"], "code": zd["code"]}):
            zone = {
                "id": _uid(), "building_id": bldg_doc["id"],
                "building_code": bldg_doc["code"], "building_name": bldg_doc["name"],
                "code": zd["code"], "name": zd["name"], "zone_type": zd["zone_type"],
                "description": "", "active": True, "created_at": _now(), "created_by": "seed",
            }
            await db.wh_zones.insert_one(zone)
            created["zones"] += 1
            zone_docs[zd["code"]] = zone
        else:
            zone_docs[zd["code"]] = await db.wh_zones.find_one({"building_id": bldg_doc["id"], "code": zd["code"]}, {"_id": 0})

    # Racks (RM zone: R01-R03, FG zone: R01-R02)
    rack_defs = [
        {"zone": "RM", "code": "R01", "name": "Rak Kain A", "shelves": 4, "slots": 6},
        {"zone": "RM", "code": "R02", "name": "Rak Kain B", "shelves": 4, "slots": 6},
        {"zone": "RM", "code": "R03", "name": "Rak Aksesori", "shelves": 5, "slots": 8},
        {"zone": "FG", "code": "R01", "name": "Rak FG Kemeja", "shelves": 4, "slots": 5},
        {"zone": "FG", "code": "R02", "name": "Rak FG Celana", "shelves": 4, "slots": 5},
    ]
    for rd in rack_defs:
        zone_doc = zone_docs.get(rd["zone"])
        if not zone_doc:
            continue
        if not await db.wh_racks.find_one({"zone_id": zone_doc["id"], "code": rd["code"]}):
            rack = {
                "id": _uid(), "zone_id": zone_doc["id"], "zone_code": zone_doc["code"],
                "zone_name": zone_doc["name"], "building_id": bldg_doc["id"],
                "building_code": bldg_doc["code"], "building_name": bldg_doc["name"],
                "code": rd["code"], "name": rd["name"],
                "num_shelves": rd["shelves"], "slots_per_shelf": rd["slots"],
                "capacity_per_slot": 0, "capacity_unit": "",
                "description": "", "active": True, "created_at": _now(), "created_by": "seed",
            }
            await db.wh_racks.insert_one(rack)
            created["racks"] += 1
            pos_count = await _generate_positions(db, rack)
            created["positions"] += pos_count

    return serialize_doc({"message": "Demo struktur gudang seeded", **created})
