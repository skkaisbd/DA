"""WebSocket manager for real-time updates.

Auth model:
- Connections authenticate via `?token=<JWT>` query param. Internal staff JWT
  is accepted via `verify_token_str`; client-portal JWT is accepted via
  `_decode_client_token`.
- Channel name `public` is allowed without a token (used for kiosk/TV-style
  read-only broadcasts). All other channels REQUIRE a valid token.
"""
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status
from typing import Dict, Set, Optional
import json
import logging

from auth import verify_token_str

logger = logging.getLogger(__name__)
router = APIRouter()

PUBLIC_CHANNELS = {"public"}


def _authenticate_ws(token: Optional[str]) -> Optional[dict]:
    """Try to validate token as either internal JWT or maklon client JWT."""
    if not token:
        return None
    payload = verify_token_str(token)
    if payload:
        return payload
    try:
        from routes.dewi_client_portal import _decode_client_token
        client_payload = _decode_client_token(token)
        if client_payload:
            return client_payload
    except Exception:  # pragma: no cover - defensive
        logger.exception("Client token decoder failed during WS auth")
    return None


class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, Set[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, channel: str = "general"):
        await websocket.accept()
        if channel not in self.active_connections:
            self.active_connections[channel] = set()
        self.active_connections[channel].add(websocket)
        logger.info(
            f"WS connected to channel '{channel}' "
            f"(total: {sum(len(v) for v in self.active_connections.values())})"
        )

    def disconnect(self, websocket: WebSocket, channel: str = "general"):
        if channel in self.active_connections:
            self.active_connections[channel].discard(websocket)

    async def broadcast(self, message: dict, channel: str = "general"):
        if channel not in self.active_connections:
            return
        dead = set()
        for connection in self.active_connections[channel]:
            try:
                await connection.send_json(message)
            except Exception:
                dead.add(connection)
        for d in dead:
            self.active_connections[channel].discard(d)

    async def broadcast_all(self, message: dict):
        for channel in list(self.active_connections.keys()):
            await self.broadcast(message, channel)


manager = ConnectionManager()


@router.websocket("/ws/{channel}")
async def websocket_endpoint(websocket: WebSocket, channel: str = "general"):
    """WebSocket entry. Public channels skip auth; otherwise require valid JWT."""
    token = websocket.query_params.get("token")
    user = _authenticate_ws(token)

    is_public = channel in PUBLIC_CHANNELS
    if not is_public and not user:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        logger.warning(
            f"WS auth failed: channel='{channel}', token_present={bool(token)}"
        )
        return

    await manager.connect(websocket, channel)
    try:
        while True:
            data = await websocket.receive_text()
            try:
                msg = json.loads(data)
                if msg.get("type") == "ping":
                    await websocket.send_json({"type": "pong"})
                else:
                    await manager.broadcast({"type": "message", "data": msg}, channel)
            except json.JSONDecodeError:
                await websocket.send_json({"type": "error", "message": "Invalid JSON"})
    except WebSocketDisconnect:
        manager.disconnect(websocket, channel)
        logger.info(f"WS disconnected from channel '{channel}'")


async def notify(event_type: str, data: dict, channel: str = "general"):
    """Send a real-time notification to connected clients."""
    await manager.broadcast({"type": event_type, "data": data}, channel)
