"""Channels CRUD + members + archive/unarchive.

Endpoints:
  GET    /api/comm/channels                         (list, supports include_archived)
  POST   /api/comm/channels                         (create)
  GET    /api/comm/channels/{channel_id}            (detail)
  PUT    /api/comm/channels/{channel_id}            (update name/desc/type) — *FIXED* in refactor
  PATCH  /api/comm/channels/{channel_id}/archive    (archive)
  PATCH  /api/comm/channels/{channel_id}/unarchive  (unarchive)
  GET    /api/comm/channels/{channel_id}/members    (list members)
  POST   /api/comm/channels/{channel_id}/members    (add)
  DELETE /api/comm/channels/{channel_id}/members/{uid}  (remove)

NOTE: In the original monolithic file (line 200-261), update_channel was BROKEN —
the update/persist/return logic was orphaned AFTER the unarchive endpoint's return,
so PUT /channels/{id} silently parsed the body but NEVER wrote to DB and returned None.
This module fixes the bug: update is properly persisted and the updated doc is returned.
"""
from fastapi import Request, HTTPException

from database import get_db
from auth import require_auth
from ._helpers import router, _uid, _now, _ser, comm_manager


@router.get("/channels")
async def list_channels(request: Request, include_archived: bool = False):
    """List channels user is a member of (or all public channels)."""
    user = await require_auth(request)
    db = get_db()
    uid = user["id"]
    base_filter: dict = {"$or": [{"members": uid}, {"type": "public"}]}
    if not include_archived:
        base_filter["archived"] = {"$ne": True}
    else:
        base_filter["archived"] = True
    channels = await db.comm_channels.find(
        base_filter, {"_id": 0}
    ).sort("updated_at", -1).to_list(200)

    result = []
    for ch in channels:
        receipt = await db.comm_read_receipts.find_one(
            {"user_id": uid, "ref_id": ch["id"]}, {"_id": 0}
        )
        last_read = receipt.get("last_read_at") if receipt else None
        query: dict = {"channel_id": ch["id"]}
        if last_read:
            query["created_at"] = {"$gt": last_read}
        unread = await db.comm_messages.count_documents(query)
        ch_out = _ser(ch)
        ch_out["unread_count"] = unread
        result.append(ch_out)
    return result


@router.post("/channels")
async def create_channel(request: Request):
    """Create a new channel."""
    user = await require_auth(request)
    db = get_db()
    body = await request.json()
    name = (body.get("name") or "").strip()
    if not name:
        raise HTTPException(400, "Nama channel wajib diisi.")
    channel_type = body.get("type", "public")  # public | private | department
    members = list(set(body.get("members", []) + [user["id"]]))

    doc = {
        "id": _uid(),
        "name": name,
        "description": (body.get("description") or "").strip(),
        "type": channel_type,
        "members": members,
        "department": body.get("department"),
        "created_by": user["id"],
        "created_by_name": user.get("name", ""),
        "archived": False,
        "created_at": _now(),
        "updated_at": _now(),
        "last_message": None,
        "last_message_at": None,
    }
    await db.comm_channels.insert_one(doc)
    return _ser(doc)


@router.get("/channels/{channel_id}")
async def get_channel(channel_id: str, request: Request):
    await require_auth(request)
    db = get_db()
    ch = await db.comm_channels.find_one({"id": channel_id}, {"_id": 0})
    if not ch:
        raise HTTPException(404, "Channel tidak ditemukan.")
    return _ser(ch)


@router.put("/channels/{channel_id}")
async def update_channel(channel_id: str, request: Request):
    """Update channel name/description/type. Only creator or admin/superadmin.

    [FIXED in Session #10 refactor]: original monolith had update/persist/return
    logic orphaned outside the function due to a bad patch; PUT silently no-op'd.
    """
    user = await require_auth(request)
    db = get_db()
    ch = await db.comm_channels.find_one({"id": channel_id})
    if not ch:
        raise HTTPException(404, "Channel tidak ditemukan.")
    if ch["created_by"] != user["id"] and user.get("role") not in ("superadmin", "admin"):
        raise HTTPException(403, "Hanya pembuat channel atau admin yang bisa mengubah.")
    body = await request.json()
    update: dict = {}
    if "name" in body and (body.get("name") or "").strip():
        update["name"] = body["name"].strip()
    if "description" in body:
        update["description"] = (body.get("description") or "").strip()
    if "type" in body and body["type"] in ("public", "private", "department"):
        update["type"] = body["type"]
    if update:
        update["updated_at"] = _now()
        await db.comm_channels.update_one({"id": channel_id}, {"$set": update})
        ch.update(update)
    return _ser(ch)


@router.patch("/channels/{channel_id}/archive")
async def archive_channel(channel_id: str, request: Request):
    """Arsipkan channel. Hanya admin/creator yang bisa."""
    user = await require_auth(request)
    db = get_db()
    ch = await db.comm_channels.find_one({"id": channel_id})
    if not ch:
        raise HTTPException(404, "Channel tidak ditemukan.")
    is_admin = user.get("role") in ("admin", "superadmin")
    is_creator = ch.get("created_by") == user["id"]
    if not (is_admin or is_creator):
        raise HTTPException(403, "Hanya pembuat channel atau admin yang bisa mengarsipkan.")
    if ch.get("archived"):
        raise HTTPException(400, "Channel sudah diarsipkan.")
    await db.comm_channels.update_one(
        {"id": channel_id},
        {"$set": {
            "archived": True,
            "archived_at": _now(),
            "archived_by": user["id"],
            "updated_at": _now(),
        }},
    )
    return {"ok": True, "archived": True}


@router.patch("/channels/{channel_id}/unarchive")
async def unarchive_channel(channel_id: str, request: Request):
    """Unarsipkan channel."""
    user = await require_auth(request)
    db = get_db()
    ch = await db.comm_channels.find_one({"id": channel_id})
    if not ch:
        raise HTTPException(404, "Channel tidak ditemukan.")
    is_admin = user.get("role") in ("admin", "superadmin")
    is_creator = ch.get("created_by") == user["id"]
    if not (is_admin or is_creator):
        raise HTTPException(403, "Hanya pembuat channel atau admin yang bisa unarchive.")
    await db.comm_channels.update_one(
        {"id": channel_id},
        {"$set": {
            "archived": False,
            "archived_at": None,
            "archived_by": None,
            "updated_at": _now(),
        }},
    )
    return {"ok": True, "archived": False}


@router.get("/channels/{channel_id}/members")
async def get_channel_members(channel_id: str, request: Request):
    """Get channel members with display info for @mention autocomplete."""
    user = await require_auth(request)
    db = get_db()
    ch = await db.comm_channels.find_one({"id": channel_id})
    if not ch:
        raise HTTPException(404, "Channel tidak ditemukan.")
    member_ids = ch.get("members", [])
    members_out = []
    for uid in member_ids:
        u = await db.users.find_one({"id": uid})
        if u:
            members_out.append({
                "id": u["id"],
                "name": u.get("name", ""),
                "email": u.get("email", ""),
                "role": u.get("role", ""),
                "department": u.get("department", ""),
                "position": u.get("position", ""),
                "is_self": uid == user["id"],
            })
    return {"members": members_out}


@router.post("/channels/{channel_id}/members")
async def add_channel_members(channel_id: str, request: Request):
    await require_auth(request)
    db = get_db()
    ch = await db.comm_channels.find_one({"id": channel_id})
    if not ch:
        raise HTTPException(404, "Channel tidak ditemukan.")
    body = await request.json()
    new_members = body.get("member_ids", [])
    await db.comm_channels.update_one(
        {"id": channel_id},
        {"$addToSet": {"members": {"$each": new_members}},
         "$set": {"updated_at": _now()}},
    )
    # Notify new members via WS
    for uid in new_members:
        await comm_manager.send_to_user(uid, {
            "type": "channel_added",
            "data": {"channel_id": channel_id, "channel_name": ch["name"]},
        })
    return {"ok": True, "added": new_members}


@router.delete("/channels/{channel_id}/members/{uid}")
async def remove_channel_member(channel_id: str, uid: str, request: Request):
    user = await require_auth(request)
    db = get_db()
    ch = await db.comm_channels.find_one({"id": channel_id})
    if not ch:
        raise HTTPException(404, "Channel tidak ditemukan.")
    if ch["created_by"] != user["id"] and uid != user["id"] and user.get("role") not in ("superadmin", "admin"):
        raise HTTPException(403, "Tidak diizinkan.")
    await db.comm_channels.update_one(
        {"id": channel_id},
        {"$pull": {"members": uid}, "$set": {"updated_at": _now()}},
    )
    return {"ok": True}
