"""Thread conversations (Slack-style nested replies).

Data model:
  - On replies: `thread_root_id` (references root message)
  - On root messages (denormalized): `thread_reply_count`, `thread_last_reply_at`,
    `thread_last_reply_by`, `thread_participants`

Endpoints:
  GET   /api/comm/messages/{root_id}/thread
  POST  /api/comm/messages/{root_id}/thread/reply
"""
import logging
import re
from fastapi import Request, HTTPException

from database import get_db
from auth import require_auth
from ._helpers import router, _uid, _now, _ser, comm_manager


@router.get("/messages/{root_id}/thread")
async def get_thread(root_id: str, request: Request):
    """Return root message + all its thread replies (oldest first)."""
    user = await require_auth(request)
    db = get_db()

    root = await db.comm_messages.find_one({"id": root_id, "deleted": {"$ne": True}})
    if not root:
        raise HTTPException(404, "Message tidak ditemukan.")

    if root.get("channel_id"):
        ch = await db.comm_channels.find_one({"id": root["channel_id"]})
        if not ch:
            raise HTTPException(404, "Channel tidak ditemukan.")
        if ch.get("type") != "public" and user["id"] not in (ch.get("members") or []):
            raise HTTPException(403, "Anda bukan anggota channel ini.")
    elif root.get("conversation_id"):
        conv = await db.comm_conversations.find_one({"id": root["conversation_id"]})
        if not conv or user["id"] not in (conv.get("participants") or []):
            raise HTTPException(403, "Anda tidak punya akses ke conversation ini.")

    replies = await db.comm_messages.find(
        {"thread_root_id": root_id, "deleted": {"$ne": True}}, {"_id": 0}
    ).sort("created_at", 1).to_list(1000)

    return {
        "root": _ser(root),
        "replies": [_ser(r) for r in replies],
        "reply_count": len(replies),
    }


@router.post("/messages/{root_id}/thread/reply")
async def post_thread_reply(root_id: str, request: Request):
    """Post a thread reply. Inherits root's channel/conversation scope.
    Updates denormalized thread_reply_count + thread_participants on the root.
    """
    user = await require_auth(request)
    db = get_db()
    body = await request.json()
    content = (body.get("content") or "").strip()
    if not content and not body.get("file_url"):
        raise HTTPException(400, "Pesan tidak boleh kosong.")

    root = await db.comm_messages.find_one({"id": root_id, "deleted": {"$ne": True}})
    if not root:
        raise HTTPException(404, "Root message tidak ditemukan.")

    # Authorization
    if root.get("channel_id"):
        ch = await db.comm_channels.find_one({"id": root["channel_id"]})
        if not ch:
            raise HTTPException(404, "Channel tidak ditemukan.")
        if ch.get("type") != "public" and user["id"] not in (ch.get("members") or []):
            raise HTTPException(403, "Anda bukan anggota channel ini.")
    elif root.get("conversation_id"):
        conv = await db.comm_conversations.find_one({"id": root["conversation_id"]})
        if not conv or user["id"] not in (conv.get("participants") or []):
            raise HTTPException(403, "Anda tidak punya akses ke conversation ini.")

    if root.get("thread_root_id"):
        raise HTTPException(400, "Tidak bisa reply pada thread reply. Gunakan root message-nya.")

    reply = {
        "id": _uid(),
        "channel_id": root.get("channel_id"),
        "conversation_id": root.get("conversation_id"),
        "thread_root_id": root_id,
        "sender_id": user["id"],
        "sender_name": user.get("name", ""),
        "sender_email": user.get("email", ""),
        "content": content,
        "message_type": body.get("message_type", "text"),
        "file_url": body.get("file_url"),
        "file_name": body.get("file_name"),
        "file_size": body.get("file_size"),
        "reactions": {},
        "edited": False,
        "deleted": False,
        "created_at": _now(),
        "updated_at": _now(),
    }
    await db.comm_messages.insert_one(reply)

    new_reply_count = (root.get("thread_reply_count") or 0) + 1
    participants = set(root.get("thread_participants") or [])
    participants.add(user["id"])
    await db.comm_messages.update_one(
        {"id": root_id},
        {"$set": {
            "thread_reply_count": new_reply_count,
            "thread_last_reply_at": _now(),
            "thread_last_reply_by": user.get("name", ""),
            "thread_participants": list(participants),
            "updated_at": _now(),
        }},
    )

    reply_out = _ser(reply)

    # Broadcast real-time update
    if root.get("channel_id"):
        ch = await db.comm_channels.find_one({"id": root["channel_id"]})
        members = ch.get("members", []) if ch else []
        await comm_manager.broadcast_to_users(members, {
            "type": "thread_reply",
            "data": {
                "reply": reply_out,
                "root_id": root_id,
                "channel_id": root["channel_id"],
                "reply_count": new_reply_count,
                "scope": "channel",
            },
        })
    elif root.get("conversation_id"):
        conv = await db.comm_conversations.find_one({"id": root["conversation_id"]})
        if conv:
            for p in conv.get("participants", []):
                await comm_manager.send_to_user(p, {
                    "type": "thread_reply",
                    "data": {
                        "reply": reply_out,
                        "root_id": root_id,
                        "conv_id": root["conversation_id"],
                        "reply_count": new_reply_count,
                        "scope": "dm",
                    },
                })

    # @mentions inside thread reply
    mentions = re.findall(r"@([\w\s\-\.]+?)(?=\s|$|@)", content + " ")
    if mentions and root.get("channel_id"):
        try:
            from routes.notifications import create_notification
            ch_doc = await db.comm_channels.find_one({"id": root["channel_id"]})
            ch_name = (ch_doc or {}).get("name", "")
            for mention_name in mentions:
                mn = mention_name.strip()
                if not mn:
                    continue
                mu = await db.users.find_one(
                    {"name": {"$regex": f"^{re.escape(mn)}$", "$options": "i"}}
                )
                if mu and mu["id"] != user["id"]:
                    await create_notification(
                        db,
                        user_id=mu["id"],
                        notif_type="mention",
                        title=f'Anda disebut oleh {user.get("name", "Seseorang")} di thread #{ch_name}',
                        content=content[:120] + ("..." if len(content) > 120 else ""),
                        source_type="thread",
                        source_id=root_id,
                        source_url=f"#/comm/thread/{root_id}",
                        metadata={
                            "channel_name": ch_name,
                            "message_id": reply["id"],
                            "thread_root_id": root_id,
                        },
                    )
        except Exception:
            logging.getLogger(__name__).debug("suppressed exception", exc_info=True)

    # Notify the original root sender (if different from replier)
    if root["sender_id"] != user["id"]:
        try:
            from routes.notifications import create_notification
            ch_name = ""
            if root.get("channel_id"):
                ch_doc = await db.comm_channels.find_one({"id": root["channel_id"]})
                ch_name = ch_doc.get("name", "") if ch_doc else ""
            await create_notification(
                db,
                user_id=root["sender_id"],
                notif_type="thread_reply",
                title=f'{user.get("name", "Seseorang")} membalas thread Anda{(" di #" + ch_name) if ch_name else ""}',
                content=content[:120] + ("..." if len(content) > 120 else ""),
                source_type="thread",
                source_id=root_id,
                source_url=f"#/comm/thread/{root_id}",
                metadata={
                    "channel_name": ch_name,
                    "message_id": reply["id"],
                    "thread_root_id": root_id,
                },
            )
        except Exception:
            logging.getLogger(__name__).debug("suppressed exception", exc_info=True)

    return reply_out
