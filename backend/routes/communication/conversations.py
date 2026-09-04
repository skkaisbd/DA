"""Direct-message conversations (1:1 DMs).

Endpoints:
  GET  /api/comm/conversations                       (list, with unread + presence)
  POST /api/comm/conversations/{other_uid}/messages  (send DM)
  GET  /api/comm/conversations/{other_uid}/messages  (history)
"""
from typing import Optional
from fastapi import Request, HTTPException, Query

from database import get_db
from auth import require_auth
from ._helpers import router, _uid, _now, _ser, comm_manager, _get_or_create_conversation


@router.get("/conversations")
async def list_conversations(request: Request):
    """List all DM conversations for current user, with unread + presence info."""
    user = await require_auth(request)
    db = get_db()
    uid = user["id"]
    convs = await db.comm_conversations.find(
        {"participants": uid}, {"_id": 0}
    ).sort("updated_at", -1).to_list(100)

    result = []
    for conv in convs:
        other_uid = next((p for p in conv["participants"] if p != uid), None)
        other_user = None
        if other_uid:
            other_user = await db.users.find_one(
                {"id": other_uid}, {"_id": 0, "name": 1, "email": 1, "id": 1}
            )
        receipt = await db.comm_read_receipts.find_one(
            {"user_id": uid, "ref_id": conv["id"]}, {"_id": 0}
        )
        last_read = receipt.get("last_read_at") if receipt else None
        q: dict = {"conversation_id": conv["id"]}
        if last_read:
            q["created_at"] = {"$gt": last_read}
        unread = await db.comm_messages.count_documents(q)

        conv_out = _ser(conv)
        conv_out["other_user"] = _ser(other_user) if other_user else {"id": other_uid, "name": "Unknown"}
        conv_out["unread_count"] = unread
        conv_out["is_online"] = other_uid in comm_manager.online_users
        result.append(conv_out)
    return result


@router.post("/conversations/{other_uid}/messages")
async def send_dm(other_uid: str, request: Request):
    user = await require_auth(request)
    db = get_db()
    body = await request.json()
    content = (body.get("content") or "").strip()
    if not content and not body.get("file_url"):
        raise HTTPException(400, "Pesan tidak boleh kosong.")

    conv = await _get_or_create_conversation(db, user["id"], other_uid)
    msg = {
        "id": _uid(),
        "channel_id": None,
        "conversation_id": conv["id"],
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
    await db.comm_conversations.update_one(
        {"id": conv["id"]},
        {"$set": {
            "last_message": content or msg["file_name"],
            "last_message_at": _now(),
            "updated_at": _now(),
        }},
    )
    msg_out = _ser(msg)
    # Notify recipient
    await comm_manager.send_to_user(other_uid, {
        "type": "new_message",
        "data": {"message": msg_out, "conv_id": conv["id"], "scope": "dm"},
    })
    return msg_out


@router.get("/conversations/{other_uid}/messages")
async def get_dm_messages(
    other_uid: str, request: Request,
    before: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=100),
    include_thread_replies: bool = Query(False),
):
    user = await require_auth(request)
    db = get_db()
    conv = await _get_or_create_conversation(db, user["id"], other_uid)
    query: dict = {"conversation_id": conv["id"], "deleted": {"$ne": True}}
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
