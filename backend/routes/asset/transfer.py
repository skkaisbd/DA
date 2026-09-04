"""Asset transfer workflow:
  POST /{asset_id}/transfer
  GET  /{asset_id}/transfer-history
"""
from fastapi import Request, HTTPException

from database import get_db
from auth import require_auth
from ._helpers import router, _uid, _now, _ser


@router.post("/{asset_id}/transfer")
async def transfer_asset(asset_id: str, request: Request):
    """Transfer asset to new location/department/employee dengan audit trail."""
    user = await require_auth(request)
    db = get_db()
    body = await request.json()

    asset = await db.dewi_assets.find_one({"id": asset_id}, {"_id": 0})
    if not asset:
        raise HTTPException(404, "Aset tidak ditemukan.")

    transfer_doc = {
        "id": _uid(),
        "asset_id": asset_id,
        "asset_number": asset["asset_number"],
        "asset_name": asset["name"],
        "from_location": asset.get("location", ""),
        "from_department": asset.get("department", ""),
        "from_employee_id": asset.get("assigned_to_id", ""),
        "from_employee_name": asset.get("assigned_to_name", ""),
        "to_location": (body.get("to_location") or "").strip(),
        "to_department": (body.get("to_department") or "").strip(),
        "to_employee_id": (body.get("to_employee_id") or "").strip(),
        "to_employee_name": (body.get("to_employee_name") or "").strip(),
        "transfer_date": body.get("transfer_date", _now().isoformat()),
        "reason": (body.get("reason") or "").strip(),
        "notes": (body.get("notes") or "").strip(),
        "transferred_by": user["id"],
        "transferred_by_name": user.get("name", ""),
        "created_at": _now(),
        "status": "completed",
    }

    await db.dewi_asset_transfers.insert_one(transfer_doc)

    update = {"updated_at": _now()}
    if body.get("to_location"):
        update["location"] = body["to_location"]
    if body.get("to_department"):
        update["department"] = body["to_department"]
    if body.get("to_employee_id"):
        update["assigned_to_id"] = body["to_employee_id"]
        update["assigned_to_name"] = body.get("to_employee_name", "")

    await db.dewi_assets.update_one({"id": asset_id}, {"$set": update})
    return {"ok": True, "transfer_id": transfer_doc["id"]}


@router.get("/{asset_id}/transfer-history")
async def get_transfer_history(asset_id: str, request: Request):
    """Riwayat transfer asset untuk audit trail."""
    await require_auth(request)
    db = get_db()
    transfers = await db.dewi_asset_transfers.find(
        {"asset_id": asset_id}, {"_id": 0}
    ).sort("created_at", -1).limit(50).to_list(50)
    return [_ser(t) for t in transfers]
