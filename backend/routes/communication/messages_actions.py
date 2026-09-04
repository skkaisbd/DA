"""Per-message actions: reactions, edit, delete, pin, unpin, get_pinned.

Endpoints:
  POST   /api/comm/messages/{msg_id}/reaction
  PATCH  /api/comm/messages/{msg_id}             (edit text)
  DELETE /api/comm/messages/{msg_id}             (delete — owner or admin)
  POST   /api/comm/messages/{msg_id}/pin
  DELETE /api/comm/messages/{msg_id}/pin
  GET    /api/comm/channels/{ch_id}/pinned       (list pinned messages in a channel)
"""
from fastapi import Request, HTTPException

from database import get_db
from auth import require_auth
from ._helpers import router, _now, _ser, comm_manager, _broadcast_msg_event


@router.post("/messages/{msg_id}/reaction")
async def toggle_reaction(msg_id: str, request: Request):
    user = await require_auth(request)
    db = get_db()
    body = await request.json()
    emoji = body.get("emoji", "")
    if not emoji:
        raise HTTPException(400, "Emoji wajib diisi.")
    msg = await db.comm_messages.find_one({"id": msg_id})
    if not msg:
        raise HTTPException(404, "Pesan tidak ditemukan.")
    reactions = msg.get("reactions", {}) or {}
    users_for_emoji = reactions.get(emoji, [])
    if user["id"] in users_for_emoji:
        users_for_emoji.remove(user["id"])
    else:
        users_for_emoji.append(user["id"])
    if not users_for_emoji:
        reactions.pop(emoji, None)
    else:
        reactions[emoji] = users_for_emoji
    await db.comm_messages.update_one(
        {"id": msg_id},
        {"$set": {"reactions": reactions, "updated_at": _now()}},
    )
    # Broadcast reaction update
    broadcast_data = {"type": "reaction_update", "data": {"msg_id": msg_id, "reactions": reactions}}
    if msg.get("channel_id"):
        ch = await db.comm_channels.find_one({"id": msg["channel_id"]}, {"members": 1})
        if ch:
            await comm_manager.broadcast_to_users(ch.get("members", []), broadcast_data)
    elif msg.get("conversation_id"):
        conv = await db.comm_conversations.find_one(
            {"id": msg["conversation_id"]}, {"participants": 1}
        )
        if conv:
            await comm_manager.broadcast_to_users(conv.get("participants", []), broadcast_data)
    return {"ok": True, "reactions": reactions}


@router.patch("/messages/{msg_id}")
async def edit_message(msg_id: str, request: Request):
    """Edit isi pesan (text). Hanya pemilik pesan yang boleh edit. Tanpa batas waktu."""
    user = await require_auth(request)
    db = get_db()
    msg = await db.comm_messages.find_one({"id": msg_id})
    if not msg:
        raise HTTPException(404, "Pesan tidak ditemukan.")
    if msg.get("sender_id") != user["id"]:
        raise HTTPException(403, "Hanya pemilik pesan yang dapat mengedit.")
    if msg.get("message_type") not in (None, "text"):
        raise HTTPException(400, "Tipe pesan ini tidak bisa diedit.")
    body = await request.json()
    new_content = (body.get("content") or "").strip()
    if not new_content:
        raise HTTPException(400, "Konten tidak boleh kosong.")
    now = _now()
    await db.comm_messages.update_one(
        {"id": msg_id},
        {"$set": {
            "content": new_content,
            "edited": True,
            "edited_at": now,
            "updated_at": now,
        }},
    )
    updated = await db.comm_messages.find_one({"id": msg_id}, {"_id": 0})
    msg_out = _ser(updated)
    await _broadcast_msg_event(db, msg, "message_edited", {"message": msg_out})
    return msg_out


@router.delete("/messages/{msg_id}")
async def delete_message(msg_id: str, request: Request):
    """Hard delete pesan. Hanya pemilik pesan (atau admin/superadmin) yang boleh."""
    user = await require_auth(request)
    db = get_db()
    msg = await db.comm_messages.find_one({"id": msg_id})
    if not msg:
        raise HTTPException(404, "Pesan tidak ditemukan.")
    is_owner = msg.get("sender_id") == user["id"]
    is_admin = (user.get("role") in ("admin", "superadmin")) or user.get("is_admin")
    if not (is_owner or is_admin):
        raise HTTPException(403, "Tidak diizinkan menghapus pesan ini.")
    await db.comm_messages.delete_one({"id": msg_id})
    # Update last_message on parent channel/conversation if needed
    if msg.get("channel_id"):
        last = await db.comm_messages.find_one(
            {"channel_id": msg["channel_id"]}, {"_id": 0}, sort=[("created_at", -1)]
        )
        await db.comm_channels.update_one(
            {"id": msg["channel_id"]},
            {"$set": {
                "last_message": (last or {}).get("content") or (last or {}).get("file_name"),
                "last_message_at": (last or {}).get("created_at"),
                "updated_at": _now(),
            }},
        )
    elif msg.get("conversation_id"):
        last = await db.comm_messages.find_one(
            {"conversation_id": msg["conversation_id"]}, {"_id": 0}, sort=[("created_at", -1)]
        )
        await db.comm_conversations.update_one(
            {"id": msg["conversation_id"]},
            {"$set": {
                "last_message": (last or {}).get("content") or (last or {}).get("file_name"),
                "last_message_at": (last or {}).get("created_at"),
                "updated_at": _now(),
            }},
        )
    await _broadcast_msg_event(db, msg, "message_deleted", {})
    return {"ok": True, "id": msg_id, "deleted": True}


@router.post("/messages/{msg_id}/pin")
async def pin_message(msg_id: str, request: Request):
    """Pin pesan di channel. Hanya admin/superadmin/member channel yang boleh."""
    user = await require_auth(request)
    db = get_db()
    msg = await db.comm_messages.find_one({"id": msg_id})
    if not msg:
        raise HTTPException(404, "Pesan tidak ditemukan.")
    if not msg.get("channel_id"):
        raise HTTPException(400, "Hanya pesan channel yang bisa di-pin.")
    ch = await db.comm_channels.find_one(
        {"id": msg["channel_id"]}, {"members": 1, "created_by": 1}
    )
    if not ch:
        raise HTTPException(404, "Channel tidak ditemukan.")
    is_admin = user.get("role") in ("admin", "superadmin") or user.get("is_admin")
    in_channel = user["id"] in ch.get("members", [])
    if not (is_admin or in_channel):
        raise HTTPException(403, "Tidak diizinkan pin pesan ini.")
    now = _now()
    await db.comm_messages.update_one(
        {"id": msg_id},
        {"$set": {
            "pinned": True,
            "pinned_by": user["id"],
            "pinned_by_name": user.get("name", ""),
            "pinned_at": now,
        }},
    )
    await db.comm_channels.update_one(
        {"id": msg["channel_id"]},
        {"$addToSet": {"pinned_message_ids": msg_id}},
    )
    await _broadcast_msg_event(db, msg, "message_pinned", {
        "pinned": True, "pinned_by_name": user.get("name", ""), "msg_id": msg_id,
    })
    return {"ok": True}


@router.delete("/messages/{msg_id}/pin")
async def unpin_message(msg_id: str, request: Request):
    """Unpin pesan dari channel."""
    user = await require_auth(request)
    db = get_db()
    msg = await db.comm_messages.find_one({"id": msg_id})
    if not msg:
        raise HTTPException(404, "Pesan tidak ditemukan.")
    if not msg.get("channel_id"):
        raise HTTPException(400, "Hanya pesan channel yang bisa di-unpin.")
    is_admin = user.get("role") in ("admin", "superadmin") or user.get("is_admin")
    is_pinner = msg.get("pinned_by") == user["id"]
    if not (is_admin or is_pinner):
        raise HTTPException(403, "Tidak diizinkan unpin pesan ini.")
    await db.comm_messages.update_one(
        {"id": msg_id},
        {"$unset": {"pinned": "", "pinned_by": "", "pinned_by_name": "", "pinned_at": ""}},
    )
    await db.comm_channels.update_one(
        {"id": msg["channel_id"]},
        {"$pull": {"pinned_message_ids": msg_id}},
    )
    await _broadcast_msg_event(db, msg, "message_unpinned", {"pinned": False, "msg_id": msg_id})
    return {"ok": True}


@router.get("/channels/{ch_id}/pinned")
async def get_pinned_messages(ch_id: str, request: Request):
    """Get all pinned messages in a channel."""
    await require_auth(request)
    db = get_db()
    ch = await db.comm_channels.find_one({"id": ch_id}, {"pinned_message_ids": 1})
    if not ch:
        raise HTTPException(404, "Channel tidak ditemukan.")
    pinned_ids = ch.get("pinned_message_ids", [])
    if not pinned_ids:
        return []
    msgs = await db.comm_messages.find(
        {"id": {"$in": pinned_ids}, "pinned": True}, {"_id": 0}
    ).to_list(None)
    return [_ser(m) for m in msgs]
