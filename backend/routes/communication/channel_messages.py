"""Channel messages: list, send (with @mention notifications), upload-file.

Endpoints:
  GET    /api/comm/channels/{channel_id}/messages
  POST   /api/comm/channels/{channel_id}/messages
  POST   /api/comm/channels/{channel_id}/upload          (file attachment uploader)
"""
import logging
import re
from typing import Optional
from fastapi import Request, HTTPException, Query, UploadFile, File

from database import get_db
from auth import require_auth
from storage import put_object, generate_storage_path
from ._helpers import router, _uid, _now, _ser, comm_manager


@router.get("/channels/{channel_id}/messages")
async def get_channel_messages(
    channel_id: str, request: Request,
    before: Optional[str] = Query(None),  # message_id cursor for pagination
    limit: int = Query(50, ge=1, le=100),
    include_thread_replies: bool = Query(
        False, description="Include thread replies in main feed (default: hide)"
    ),
):
    await require_auth(request)
    db = get_db()
    ch = await db.comm_channels.find_one({"id": channel_id})
    if not ch:
        raise HTTPException(404, "Channel tidak ditemukan.")
    query: dict = {"channel_id": channel_id, "deleted": {"$ne": True}}
    if not include_thread_replies:
        query["$or"] = [
            {"thread_root_id": {"$exists": False}},
            {"thread_root_id": None},
        ]
    if before:
        anchor = await db.comm_messages.find_one({"id": before})
        if anchor:
            existing_created_at = query.get("created_at", {})
            existing_created_at["$lt"] = anchor["created_at"]
            query["created_at"] = existing_created_at
    msgs = await db.comm_messages.find(
        query, {"_id": 0}
    ).sort("created_at", -1).limit(limit).to_list(limit)
    msgs.reverse()
    return [_ser(m) for m in msgs]


@router.post("/channels/{channel_id}/messages")
async def send_channel_message(channel_id: str, request: Request):
    user = await require_auth(request)
    db = get_db()
    ch = await db.comm_channels.find_one({"id": channel_id})
    if not ch:
        raise HTTPException(404, "Channel tidak ditemukan.")
    body = await request.json()
    content = (body.get("content") or "").strip()
    if not content and not body.get("file_url"):
        raise HTTPException(400, "Pesan tidak boleh kosong.")

    msg = {
        "id": _uid(),
        "channel_id": channel_id,
        "conversation_id": None,
        "sender_id": user["id"],
        "sender_name": user.get("name", ""),
        "sender_email": user.get("email", ""),
        "content": content,
        "message_type": body.get("message_type", "text"),
        "file_url": body.get("file_url"),
        "file_name": body.get("file_name"),
        "file_size": body.get("file_size"),
        "reply_to_id": body.get("reply_to_id"),
        "reply_to_preview": body.get("reply_to_preview"),
        "reactions": {},
        "edited": False,
        "deleted": False,
        "created_at": _now(),
        "updated_at": _now(),
    }
    await db.comm_messages.insert_one(msg)
    await db.comm_channels.update_one(
        {"id": channel_id},
        {"$set": {
            "last_message": content or msg["file_name"],
            "last_message_at": _now(),
            "updated_at": _now(),
        }},
    )
    msg_out = _ser(msg)

    # Real-time broadcast to channel members
    members = ch.get("members", [])
    await comm_manager.broadcast_to_users(members, {
        "type": "new_message",
        "data": {"message": msg_out, "channel_id": channel_id, "scope": "channel"},
    })

    # @mentions: notification to mentioned users
    mentions = re.findall(r"@([\w\s\-\.]+?)(?=\s|$|@)", content + " ")
    if mentions:
        try:
            from routes.notifications import create_notification
            for mention_name in mentions:
                mn = mention_name.strip()
                if not mn:
                    continue
                mentioned_user = await db.users.find_one(
                    {"name": {"$regex": f"^{re.escape(mn)}$", "$options": "i"}}
                )
                if mentioned_user and mentioned_user["id"] != user["id"]:
                    channel_name = ch.get("name", channel_id)
                    await create_notification(
                        db,
                        user_id=mentioned_user["id"],
                        notif_type="mention",
                        title=f'Anda disebut oleh {user.get("name", "Seseorang")} di #{channel_name}',
                        content=content[:120] + ("..." if len(content) > 120 else ""),
                        source_type="channel",
                        source_id=channel_id,
                        source_url=f"#/comm/channel/{channel_id}",
                        metadata={"channel_name": channel_name, "message_id": msg["id"]},
                    )
        except Exception:
            logging.getLogger(__name__).debug("suppressed exception", exc_info=True)
    return msg_out


@router.post("/channels/{channel_id}/upload")
async def upload_file_message(channel_id: str, request: Request, file: UploadFile = File(...)):
    """Upload file attachment for a channel message (max 10 MB)."""
    await require_auth(request)
    db = get_db()
    ch = await db.comm_channels.find_one({"id": channel_id})
    if not ch:
        raise HTTPException(404, "Channel tidak ditemukan.")
    if file.size and file.size > 10 * 1024 * 1024:
        raise HTTPException(400, "Ukuran file maksimal 10 MB.")
    content_bytes = await file.read()
    storage_path = generate_storage_path(f"comm/{channel_id}", file.filename)
    stored = put_object(storage_path, content_bytes, file.content_type or "application/octet-stream")
    return {
        "file_url": stored["url"],
        "file_name": file.filename,
        "file_size": len(content_bytes),
        "content_type": file.content_type,
    }
