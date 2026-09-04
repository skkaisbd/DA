"""
Shared utility helpers for CV. Dewi Aditya ERP.

Centralizes common patterns used across route modules:
- UUID generation
- UTC-aware now()
- MongoDB document cleaning (strip _id)
- Sequential code generation with date prefix
- Safe numeric coercion
"""
from datetime import datetime, timezone, date
from typing import Any, Dict, List, Optional
import uuid


def _uid() -> str:
    """Generate a new UUID4 string (used as primary `id` for MongoDB docs)."""
    return str(uuid.uuid4())


def _now() -> datetime:
    """Return current UTC timezone-aware datetime (MongoDB safe)."""
    return datetime.now(timezone.utc)


def _today_iso() -> str:
    """Return today's date in ISO format YYYY-MM-DD."""
    return date.today().isoformat()


def _clean(doc: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Strip MongoDB `_id` field from a document (returns same dict for convenience)."""
    if not doc:
        return doc
    doc.pop('_id', None)
    return doc


def _clean_list(docs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Strip _id from a list of documents."""
    return [_clean(d) for d in docs]


async def _next_code(db, prefix: str, coll: str, field: str) -> str:
    """
    Generate a sequential code with date prefix, e.g. 'CUT-20260430-003'.
    Reads current count from MongoDB collection (idempotent per-day).

    Note: not race-safe if multiple concurrent requests hit this in the same ms.
    For production use cases needing guaranteed uniqueness, use a counter collection
    with find_one_and_update + $inc (see dewi_maklon_billing._next_invoice_number).
    """
    today = date.today().strftime('%Y%m%d')
    base = f"{prefix}-{today}-"
    docs = await db[coll].count_documents({field: {"$regex": f"^{base}"}})
    return f"{base}{str(docs + 1).zfill(3)}"


def _to_int(value: Any, default: int = 0) -> int:
    """Safely coerce a value to int with fallback."""
    try:
        return int(value)
    except (ValueError, TypeError):
        return default


def _to_float(value: Any, default: float = 0.0) -> float:
    """Safely coerce a value to float with fallback."""
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


def user_display_name(user: Dict[str, Any]) -> str:
    """Resolve a display name from a JWT user dict (falls back through name → email)."""
    return user.get('name') or user.get('email') or 'unknown'
