"""Shared generic helpers used across route modules.

Moved out of server.py during Backend Refactor Phase 0 (see /app/BACKEND_REFACTOR_PLAN.md).
Pure move — behavior is byte-for-byte identical to the original definitions in server.py.
"""
import uuid
from datetime import datetime, timezone


def new_id():
    return str(uuid.uuid4())


def now():
    return datetime.now(timezone.utc)


def parse_date(d):
    if not d: return None
    if isinstance(d, datetime): return d
    try: return datetime.fromisoformat(str(d).replace('Z', '+00:00'))
    except Exception: return None


def to_end_of_day(d):
    if isinstance(d, str):
        d = parse_date(d)
    if d:
        return d.replace(hour=23, minute=59, second=59, microsecond=999999)
    return None
