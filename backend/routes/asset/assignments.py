"""Assignment + maintenance per asset.

Endpoints:
  POST /{asset_id}/assign
  POST /{asset_id}/unassign
  GET  /{asset_id}/assignments
  POST /{asset_id}/maintenance
  GET  /{asset_id}/maintenance
"""
from datetime import date
from fastapi import Request, HTTPException

from database import get_db
from auth import require_auth
from ._helpers import router, _uid, _now, _ser


@router.post("/{asset_id}/assign")
async def assign_asset(asset_id: str, request: Request):
    user = await require_auth(request)
    db = get_db()
    asset = await db.dewi_assets.find_one({"id": asset_id})
    if not asset:
        raise HTTPException(404, "Aset tidak ditemukan.")
    body = await request.json()
    assign_to_id = body.get("user_id") or ""
    assign_to_name = body.get("user_name") or ""
    if not assign_to_id:
        raise HTTPException(400, "ID karyawan wajib diisi.")

    assn_doc = {
        "id": _uid(),
        "asset_id": asset_id,
        "asset_name": asset["name"],
        "asset_number": asset["asset_number"],
        "assigned_to_id": assign_to_id,
        "assigned_to_name": assign_to_name,
        "assigned_by_id": user["id"],
        "assigned_by_name": user.get("name", ""),
        "assigned_date": (body.get("assigned_date") or date.today().isoformat())[:10],
        "returned_date": None,
        "notes": (body.get("notes") or "").strip(),
        "status": "active",
        "created_at": _now(),
    }
    await db.dewi_asset_assignments.insert_one(assn_doc)
    await db.dewi_assets.update_one(
        {"id": asset_id},
        {"$set": {"assigned_to_id": assign_to_id, "assigned_to_name": assign_to_name, "updated_at": _now()}},
    )
    return _ser(assn_doc)


@router.post("/{asset_id}/unassign")
async def unassign_asset(asset_id: str, request: Request):
    await require_auth(request)
    db = get_db()
    asset = await db.dewi_assets.find_one({"id": asset_id})
    if not asset:
        raise HTTPException(404, "Aset tidak ditemukan.")
    today = date.today().isoformat()
    await db.dewi_asset_assignments.update_many(
        {"asset_id": asset_id, "status": "active"},
        {"$set": {"status": "returned", "returned_date": today}},
    )
    await db.dewi_assets.update_one(
        {"id": asset_id},
        {"$set": {"assigned_to_id": None, "assigned_to_name": None, "updated_at": _now()}},
    )
    return {"ok": True}


@router.get("/{asset_id}/assignments")
async def get_asset_assignments(asset_id: str, request: Request):
    await require_auth(request)
    db = get_db()
    recs = await db.dewi_asset_assignments.find(
        {"asset_id": asset_id}, {"_id": 0}
    ).sort("assigned_date", -1).to_list(100)
    return [_ser(r) for r in recs]


@router.post("/{asset_id}/maintenance")
async def add_maintenance(asset_id: str, request: Request):
    user = await require_auth(request)
    db = get_db()
    asset = await db.dewi_assets.find_one({"id": asset_id})
    if not asset:
        raise HTTPException(404, "Aset tidak ditemukan.")
    body = await request.json()
    doc = {
        "id": _uid(),
        "asset_id": asset_id,
        "asset_name": asset["name"],
        "type": body.get("type", "corrective"),
        "description": (body.get("description") or "").strip(),
        "cost": float(body.get("cost") or 0),
        "performed_by": (body.get("performed_by") or "").strip(),
        "maintenance_date": (body.get("maintenance_date") or date.today().isoformat())[:10],
        "next_scheduled": body.get("next_scheduled"),
        "status": body.get("status", "completed"),
        "notes": (body.get("notes") or "").strip(),
        "created_by": user["id"],
        "created_at": _now(),
    }
    await db.dewi_asset_maintenance.insert_one(doc)
    if doc["status"] == "in_progress":
        await db.dewi_assets.update_one({"id": asset_id}, {"$set": {"status": "in_maintenance", "updated_at": _now()}})
    elif doc["status"] == "completed" and asset.get("status") == "in_maintenance":
        await db.dewi_assets.update_one({"id": asset_id}, {"$set": {"status": "active", "updated_at": _now()}})
    return _ser(doc)


@router.get("/{asset_id}/maintenance")
async def get_maintenance_history(asset_id: str, request: Request):
    await require_auth(request)
    db = get_db()
    recs = await db.dewi_asset_maintenance.find(
        {"asset_id": asset_id}, {"_id": 0}
    ).sort("maintenance_date", -1).to_list(100)
    return [_ser(r) for r in recs]
