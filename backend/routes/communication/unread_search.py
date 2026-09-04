"""Unread tracking, read-receipts, message search, online users.

Endpoints:
  GET   /api/comm/unread                (all-rooms unread counts)
  POST  /api/comm/read/{ref_id}         (mark channel/DM as read)
  GET   /api/comm/search?q=&channel_id  (content search)
  GET   /api/comm/online-users
"""
from typing import Optional
from fastapi import Request, Query

from database import get_db
from auth import require_auth
from ._helpers import router, _now, _ser, comm_manager


@router.get("/unread")
async def get_unread_counts(request: Request):
    """Get unread message counts per channel and per DM conversation."""
    user = await require_auth(request)
    db = get_db()
    uid = user["id"]
    receipts = await db.comm_read_receipts.find({"user_id": uid}, {"_id": 0}).to_list(500)
    read_map = {r["ref_id"]: r.get("last_read_at") for r in receipts}

    channels = await db.comm_channels.find(
        {"$or": [{"members": uid}, {"type": "public"}]}, {"id": 1, "_id": 0}
    ).to_list(200)
    channel_counts = {}
    for ch in channels:
        q: dict = {"channel_id": ch["id"]}
        lr = read_map.get(ch["id"])
        if lr:
            q["created_at"] = {"$gt": lr}
        channel_counts[ch["id"]] = await db.comm_messages.count_documents(q)

    convs = await db.comm_conversations.find(
        {"participants": uid}, {"id": 1, "_id": 0}
    ).to_list(200)
    dm_counts = {}
    for conv in convs:
        q = {"conversation_id": conv["id"]}
        lr = read_map.get(conv["id"])
        if lr:
            q["created_at"] = {"$gt": lr}
        dm_counts[conv["id"]] = await db.comm_messages.count_documents(q)

    return {"channels": channel_counts, "dms": dm_counts}


@router.post("/read/{ref_id}")
async def mark_as_read(ref_id: str, request: Request):
    """Mark all messages in a channel or DM conversation as read."""
    user = await require_auth(request)
    db = get_db()
    await db.comm_read_receipts.update_one(
        {"user_id": user["id"], "ref_id": ref_id},
        {"$set": {
            "user_id": user["id"],
            "ref_id": ref_id,
            "last_read_at": _now(),
        }},
        upsert=True,
    )
    return {"ok": True}


@router.get("/search")
async def search_messages(
    request: Request,
    q: str = Query(""),
    channel_id: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=50),
):
    """Search message content (case-insensitive regex) across channels or in a specific channel."""
    await require_auth(request)
    db = get_db()
    if not q.strip():
        return []
    query: dict = {
        "content": {"$regex": q.strip(), "$options": "i"},
        "deleted": {"$ne": True},
    }
    if channel_id:
        query["channel_id"] = channel_id
    msgs = await db.comm_messages.find(
        query, {"_id": 0}
    ).sort("created_at", -1).limit(limit).to_list(limit)
    return [_ser(m) for m in msgs]


@router.get("/online-users")
async def get_online_users(request: Request):
    """Return list of currently online user IDs (via active WS connections)."""
    await require_auth(request)
    return {"online_user_ids": comm_manager.get_online_user_ids()}
