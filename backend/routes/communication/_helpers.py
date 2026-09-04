"""
Shared infrastructure for Communication Hub:
- The FastAPI router instance
- The WebSocket connection manager (singleton: `comm_manager`)
- Tiny utilities (_uid, _now, _ser)
- The DM conversation get-or-create helper
- The cross-module event broadcaster
- Index creator (called at startup)

Exported names that are imported by OTHER modules in the codebase
(must NOT change to preserve backward compat):
  - router
  - comm_manager
  - _get_or_create_conversation
  - create_comm_indexes
"""
from datetime import datetime, timezone
import uuid
import logging

from fastapi import APIRouter, WebSocket

logger = logging.getLogger("comm_hub")

# ─── Router (shared across all communication sub-modules) ────────────────────────
router = APIRouter(prefix="/api/comm", tags=["communication-hub"])


# ─── Tiny utilities ──────────────────────────────────────────────────────
def _uid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _ser(doc):
    """Strip Mongo `_id` and stringify datetimes for safe JSON serialization."""
    if not doc:
        return doc
    doc = {k: v for k, v in doc.items() if k != "_id"}
    for k, v in doc.items():
        if isinstance(v, datetime):
            doc[k] = v.isoformat()
    return doc


# ─── WebSocket Connection Manager (singleton) ──────────────────────────────────
class CommConnectionManager:
    """Multi-room WebSocket manager. Each user can have multiple connections (tabs)."""

    def __init__(self):
        # user_id -> list[WebSocket]
        self.connections: dict[str, list] = {}
        # set of online user_ids
        self.online_users: set = set()

    async def connect(self, ws: WebSocket, user_id: str, user_name: str):
        await ws.accept()
        if user_id not in self.connections:
            self.connections[user_id] = []
        self.connections[user_id].append(ws)
        self.online_users.add(user_id)
        logger.info(f"[CommWS] {user_name} connected. Online: {len(self.online_users)}")

    def disconnect(self, ws: WebSocket, user_id: str):
        if user_id in self.connections:
            try:
                self.connections[user_id].remove(ws)
            except ValueError:
                logging.getLogger(__name__).debug("suppressed exception", exc_info=True)
            if not self.connections[user_id]:
                del self.connections[user_id]
                self.online_users.discard(user_id)

    async def send_to_user(self, user_id: str, data: dict):
        if user_id not in self.connections:
            return
        dead = []
        for ws in list(self.connections.get(user_id, [])):
            try:
                await ws.send_json(data)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws, user_id)

    async def broadcast_to_users(self, user_ids: list, data: dict):
        for uid in user_ids:
            await self.send_to_user(uid, data)

    async def broadcast_presence(self, user_id: str, user_name: str, is_online: bool):
        """Notify all online users about presence change."""
        all_users = list(self.connections.keys())
        payload = {
            "type": "presence",
            "data": {"user_id": user_id, "name": user_name, "online": is_online},
        }
        for uid in all_users:
            if uid != user_id:
                await self.send_to_user(uid, payload)

    def get_online_user_ids(self) -> list:
        return list(self.online_users)


# Singleton — imported by routes/dewi_procurement.py and other modules
comm_manager = CommConnectionManager()


# ─── DM conversation helper (imported by dewi_procurement.py too) ─────────────────
async def _get_or_create_conversation(db, uid1: str, uid2: str) -> dict:
    """Get or create a 1:1 DM conversation between two users."""
    participants = sorted([uid1, uid2])
    conv = await db.comm_conversations.find_one({"participants": participants}, {"_id": 0})
    if not conv:
        conv = {
            "id": _uid(),
            "participants": participants,
            "created_at": _now(),
            "updated_at": _now(),
            "last_message": None,
            "last_message_at": None,
        }
        await db.comm_conversations.insert_one(conv)
    return conv


# ─── Internal: broadcast message event to channel members / DM peers ───────────────
async def _broadcast_msg_event(db, msg: dict, event_type: str, payload_extra: dict):
    """Broadcast event ke seluruh member channel/peserta DM."""
    data = {"type": event_type, "data": {"msg_id": msg["id"], **payload_extra}}
    if msg.get("channel_id"):
        ch = await db.comm_channels.find_one({"id": msg["channel_id"]}, {"members": 1})
        if ch:
            await comm_manager.broadcast_to_users(ch.get("members", []), data)
    elif msg.get("conversation_id"):
        conv = await db.comm_conversations.find_one(
            {"id": msg["conversation_id"]}, {"participants": 1}
        )
        if conv:
            await comm_manager.broadcast_to_users(conv.get("participants", []), data)


# ─── Index creation (called at server startup) ──────────────────────────────
async def create_comm_indexes(db):
    await db.comm_channels.create_index([("members", 1), ("archived", 1)])
    await db.comm_channels.create_index([("type", 1), ("archived", 1)])
    await db.comm_messages.create_index([("channel_id", 1), ("created_at", -1)])
    await db.comm_messages.create_index([("conversation_id", 1), ("created_at", -1)])
    await db.comm_conversations.create_index([("participants", 1)])
    await db.comm_read_receipts.create_index(
        [("user_id", 1), ("ref_id", 1)], unique=True
    )
