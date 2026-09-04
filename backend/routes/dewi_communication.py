"""
CV. Dewi Aditya ERP — Communication Hub (Thin Orchestrator).

[REFACTORED 2026-05-24 — was 1141 LOC monolith; now split into routes/communication/*]

Responsibilities of this thin file:
  1. Re-export `router`, `comm_manager`, `_get_or_create_conversation`, `create_comm_indexes`
     from `routes.communication._helpers` (the public API external code consumes).
  2. Trigger endpoint registration by importing each sub-module.

No behavior change — every endpoint preserves its original path, method,
request schema, and response shape. Backed by the SAME MongoDB collections:
  comm_channels, comm_messages, comm_conversations, comm_read_receipts

Bug fix bonus (Session #10): `PUT /api/comm/channels/{channel_id}` was BROKEN
in the original monolith — the update/persist/return logic was orphaned outside
the function due to a previous bad patch (lines 200-261 in the original file).
The refactored `channels.py` fixes this; PUT now properly persists and returns
the updated channel doc.

Endpoint groups (file-by-file):
  channels.py           → /channels (list/create/get/update/archive/unarchive),
                          /channels/{id}/members (list/add/remove)
  channel_messages.py   → /channels/{id}/messages (list/send), /channels/{id}/upload
  conversations.py      → /conversations (list), /conversations/{uid}/messages (send/get)
  threads.py            → /messages/{root_id}/thread (get), /messages/{root_id}/thread/reply (post)
  messages_actions.py   → /messages/{id}/reaction, /messages/{id} (PATCH/DELETE),
                          /messages/{id}/pin (POST/DELETE), /channels/{id}/pinned (GET)
  unread_search.py      → /unread, /read/{ref_id}, /search, /online-users
  websocket.py          → /ws  (WebSocket real-time hub)
"""
# Public API consumed by other modules (server.py, dewi_procurement.py, etc.) —
# preserve these names exactly:
from routes.communication._helpers import (  # noqa: F401
    router,
    comm_manager,
    _get_or_create_conversation,
    create_comm_indexes,
)

# Trigger endpoint registration on the shared `router` instance.
# No route-priority issues here (literal paths and {id} catch-alls in this
# router never collide on the same prefix — each has a distinct suffix).
from routes.communication import channels            # noqa: F401, E402
from routes.communication import channel_messages    # noqa: F401, E402
from routes.communication import conversations       # noqa: F401, E402
from routes.communication import threads             # noqa: F401, E402
from routes.communication import messages_actions    # noqa: F401, E402
from routes.communication import unread_search       # noqa: F401, E402
from routes.communication import websocket           # noqa: F401, E402

__all__ = [
    "router",
    "comm_manager",
    "_get_or_create_conversation",
    "create_comm_indexes",
]
