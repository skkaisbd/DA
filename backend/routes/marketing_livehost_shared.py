# ruff: noqa: F401
"""
marketing_livehost_shared.py — Shared Helpers, Models & Constants
Extracted from marketing_livehost.py (2278 LOC monolith)

Refactored: Session #11.19 Phase 3.2 Batch #2
"""
import uuid
import os
from datetime import datetime, timezone, timedelta
from typing import Optional, List
from fastapi import HTTPException, Request
from pydantic import BaseModel, Field
from database import get_db
from auth import JWT_SECRET
import jwt as pyjwt
import logging

logger = logging.getLogger(__name__)

# Constants
LIVEHOST_TOKEN_AUDIENCE = 'livehost-portal'
LIVEHOST_TOKEN_HOURS = 24
UPLOAD_DIR = '/app/uploads/livehost'
UUID_PATH_REGEX = r'^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$'

# Ensure upload directory exists
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(f'{UPLOAD_DIR}/scripts', exist_ok=True)
os.makedirs(f'{UPLOAD_DIR}/training', exist_ok=True)

# Notification SSOT integration
from utils.notif_unified import (  # noqa: E402
    notif_insert as _notif_insert_ssot,
    reshape_as_livehost as _reshape_lh_notif,
)

# Helpers
def _uid():
    return str(uuid.uuid4())

def _now():
    return datetime.now(timezone.utc)

def _get_user(request: Request) -> dict:
    return getattr(request.state, 'user', {"id": "system", "email": "system"})

def _create_livehost_token(host_id: str, host_name: str, host_email: str) -> str:
    """Create JWT token for LiveHost portal authentication"""
    payload = {
        'host_id': host_id,
        'host_name': host_name,
        'host_email': host_email,
        'aud': LIVEHOST_TOKEN_AUDIENCE,
        'exp': datetime.now(timezone.utc) + timedelta(hours=LIVEHOST_TOKEN_HOURS)
    }
    return pyjwt.encode(payload, JWT_SECRET, algorithm='HS256')

def _decode_livehost_token(token: str) -> dict:
    """Decode and validate LiveHost JWT token"""
    try:
        return pyjwt.decode(token, JWT_SECRET, algorithms=['HS256'], audience=LIVEHOST_TOKEN_AUDIENCE)
    except pyjwt.PyJWTError as e:
        raise HTTPException(401, f"Invalid token: {str(e)}")

async def require_livehost_auth(request: Request) -> dict:
    """Require valid LiveHost portal authentication"""
    auth_header = request.headers.get('Authorization', '')
    if not auth_header.startswith('Bearer '):
        raise HTTPException(401, "Missing or invalid Authorization header")
    token = auth_header.split(' ', 1)[1]
    payload = _decode_livehost_token(token)
    # Normalize keys: token uses host_id/host_name/host_email → expose as id/name/email
    return {
        'id': payload.get('host_id', ''),
        'name': payload.get('host_name', ''),
        'email': payload.get('host_email', ''),
        'assigned_account_ids': payload.get('assigned_account_ids', []),
        **payload,
    }

# Pydantic Models
class LiveHostCreate(BaseModel):
    # Aligned with create_livehost endpoint & AddEditHostModal (FE).
    name: str
    email: str
    password: str
    phone: Optional[str] = None
    employment_type: str = "part_time"
    # FASE 14 — `ge=0` WAJIB: tanpa batas ini `hourly_rate: -75000` diterima
    # HTTP 200 dan TERSIMPAN. Nilai itu dipakai langsung di
    # marketing_livehost_analytics.py: `base_pay = actual_hours * hourly_rate`
    # ⇒ GAJI NEGATIF. Bukti & cara uji ulang: scripts/probe_numeric_bounds.py
    hourly_rate: float = Field(0, ge=0)
    # SESI #34 — host live digaji BULANAN dan gajinya milik payroll HR. Marketing
    # hanya MENAUTKAN host ke karyawan HR (`employee_id`); nominalnya dibaca dari
    # `rahaza_employees` supaya tidak ada dua angka gaji untuk satu orang.
    employee_id: Optional[str] = None
    monthly_salary: float = Field(0, ge=0)
    shift_preferences: Optional[List[str]] = None
    language_skills: Optional[List[str]] = None
    product_expertise: Optional[List[str]] = None
    assigned_account_ids: Optional[List[str]] = None
    notes: Optional[str] = None

class LiveHostUpdate(BaseModel):
    # Aligned with update_livehost endpoint & AddEditHostModal (FE). All optional.
    employee_id: Optional[str] = None
    monthly_salary: Optional[float] = Field(None, ge=0)
    name: Optional[str] = None
    email: Optional[str] = None
    password: Optional[str] = None
    phone: Optional[str] = None
    employment_type: Optional[str] = None
    # FASE 14 — endpoint UPDATE (`PATCH /api/marketing/livehost/{id}`) menulis
    # nilai ini langsung ke DB tanpa guard, sama berbahayanya dengan CREATE.
    hourly_rate: Optional[float] = Field(default=None, ge=0)
    shift_preferences: Optional[List[str]] = None
    language_skills: Optional[List[str]] = None
    product_expertise: Optional[List[str]] = None
    assigned_account_ids: Optional[List[str]] = None
    status: Optional[str] = None
    notes: Optional[str] = None

class ShiftCreate(BaseModel):
    # Aligned with create_shift endpoint & AddShiftModal (FE).
    host_id: str
    account_id: str
    date: str
    shift_type: str = "morning"
    shift_start_time: str
    shift_end_time: str
    notes: Optional[str] = None

class ShiftUpdate(BaseModel):
    # Aligned with update_shift (PATCH) endpoint. All optional.
    host_id: Optional[str] = None
    account_id: Optional[str] = None
    date: Optional[str] = None
    shift_type: Optional[str] = None
    shift_start_time: Optional[str] = None
    shift_end_time: Optional[str] = None
    status: Optional[str] = None
    notes: Optional[str] = None

class ClockInOut(BaseModel):
    # host_id optional: portal derives host from token; admin may pass it.
    shift_id: str
    action: str  # 'clock_in' | 'clock_out'
    host_id: Optional[str] = None

class ShiftPerformanceRecord(BaseModel):
    # Aligned with record_shift_performance endpoint & RecordPerformanceModal /
    # LiveHost portal self-report.
    shift_id: str
    platform: Optional[str] = None
    viewers: int = 0
    peak_viewers: int = 0
    revenue: float = 0
    orders: int = 0
    items_promoted: Optional[List[str]] = None
    script_ids_used: Optional[List[str]] = None
    script_adherence_score: Optional[float] = None
    challenges_faced: Optional[str] = None
    notes: Optional[str] = None

class ScriptCreate(BaseModel):
    title: str
    content: str
    category: Optional[str] = None

class TrainingCreate(BaseModel):
    title: str
    description: Optional[str] = None
    content_url: Optional[str] = None

class TrainingAssign(BaseModel):
    training_id: str
    host_ids: list

class TrainingComplete(BaseModel):
    notes: Optional[str] = None

class LiveHostLoginIn(BaseModel):
    email: str
    password: str


# ══════════════════════════════════════════════════════════════════════════════
# PORTAL LOGIN RATE-LIMITING (Brute-force protection)
# ══════════════════════════════════════════════════════════════════════════════

# Brute-force protection for portal login
# {identifier: {'attempts': count, 'locked_until': datetime}}
PORTAL_LOGIN_ATTEMPTS: dict = {}
MAX_LOGIN_ATTEMPTS = 5
LOCKOUT_DURATION_MINUTES = 15


# ══════════════════════════════════════════════════════════════════════════════
# LIVEHOST SSE NOTIFICATION SYSTEM
# (Moved here from marketing_livehost_portal.py — Session #11.20 recovery)
# Sub-modules (shifts, training, analytics) need access without circular import.
# ══════════════════════════════════════════════════════════════════════════════

# In-memory subscriber registry: host_id → asyncio.Queue
_livehost_sse_subscribers: dict = {}


async def publish_livehost_notification(
    db,
    *,
    host_id: str,
    type_: str,
    title: str,
    message: str,
    severity: str = 'info',
    link: Optional[str] = None,
):
    """
    Persist a LiveHost notification to SSOT (`notifications`, type='marketing_livehost')
    + push to live SSE subscribers.

    Called from: shift creation/update, training assignment, payment sync, etc.
    """
    nid = _uid()
    norm_severity = severity if severity in ('info', 'success', 'warning', 'error') else 'info'
    notif = {
        'id': nid,
        'host_id': host_id,
        'type': type_,
        'severity': norm_severity,
        'title': title,
        'message': message,
        'link': link,
        'read': False,
        'created_at': _now().isoformat(),
    }
    try:
        await _notif_insert_ssot(
            db,
            id=nid,
            type='marketing_livehost',
            body=message,
            subtype=type_,
            severity=norm_severity,
            title=title,
            channel='sse',
            source_type='marketing_livehost',
            source_id=host_id,
            source_url=link,
            host_id=host_id,
        )
    except Exception:
        # Non-fatal: failure to persist must not break the originating action
        logging.getLogger(__name__).debug("suppressed exception", exc_info=True)

    # Push to live SSE subscribers for this host
    q = _livehost_sse_subscribers.get(host_id)
    if q is not None:
        try:
            q.put_nowait(notif)
        except Exception:
            logging.getLogger(__name__).debug("suppressed exception", exc_info=True)
    return notif
