"""Comm Hub WebSocket endpoint: real-time chat updates.

Client → Server: {"type": "ping"|"typing", ...}
Server → Client (event types):
  - "new_message"      : new channel/DM message
  - "reaction_update"  : reaction changed on a message
  - "presence"         : user online/offline
  - "channel_added"    : added to a new channel
  - "thread_reply"     : new reply in a thread
  - "message_edited"   : message content edited
  - "message_deleted"  : message deleted
  - "message_pinned"   : message pinned in channel
  - "message_unpinned" : message unpinned
  - "typing"           : someone is typing in a channel
  - "ping"             : server keep-alive (after 30s idle)
"""
import asyncio
import json
import logging
from fastapi import WebSocket, WebSocketDisconnect

from database import get_db
from auth import verify_token_str
from ._helpers import router, comm_manager

logger = logging.getLogger("comm_hub.ws")


@router.websocket("/ws")
async def comm_websocket(ws: WebSocket, token: str = ""):
    """WebSocket endpoint untuk Communication Hub."""
    if not token:
        await ws.close(code=4001, reason="Token required")
        return
    user = verify_token_str(token)
    if not user:
        await ws.close(code=4001, reason="Invalid token")
        return

    user_id = user["id"]
    user_name = user.get("name", "")

    await comm_manager.connect(ws, user_id, user_name)
    # Broadcast presence to others
    await comm_manager.broadcast_presence(user_id, user_name, True)

    try:
        while True:
            try:
                data = await asyncio.wait_for(ws.receive_text(), timeout=30.0)
                # Handle client-sent messages (keep-alive, typing, etc.)
                try:
                    payload = json.loads(data)
                    if payload.get("type") == "typing":
                        channel_id = payload.get("channel_id")
                        if channel_id:
                            db = get_db()
                            ch = await db.comm_channels.find_one(
                                {"id": channel_id}, {"members": 1}
                            )
                            if ch:
                                others = [m for m in ch.get("members", []) if m != user_id]
                                await comm_manager.broadcast_to_users(others, {
                                    "type": "typing",
                                    "data": {
                                        "user_id": user_id,
                                        "user_name": user_name,
                                        "channel_id": channel_id,
                                    },
                                })
                except Exception:
                    logging.getLogger(__name__).debug("suppressed exception", exc_info=True)
            except asyncio.TimeoutError:
                await ws.send_json({"type": "ping"})
    except WebSocketDisconnect:
        logging.getLogger(__name__).debug("suppressed exception", exc_info=True)
    except Exception as e:
        logger.warning(f"[CommWS] Error for {user_name}: {e}")
    finally:
        comm_manager.disconnect(ws, user_id)
        await comm_manager.broadcast_presence(user_id, user_name, False)
