"""marketing_kol — shared router, constants, Pydantic models, helper functions."""
# ruff: noqa: E741
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from database import get_db
from auth import JWT_SECRET, verify_password, require_auth, serialize_doc  # noqa: F401
import jwt as pyjwt

router = APIRouter(prefix='/api/marketing', tags=['Marketing-KOL'])

CREATOR_TOKEN_AUDIENCE = 'creator-portal'
CREATOR_TOKEN_HOURS = 24
CREATOR_LOGIN_MAX_ATTEMPTS = 5
CREATOR_LOGIN_LOCKOUT_MINUTES = 15


def _uid():
    return str(uuid.uuid4())


def _now():
    return datetime.now(timezone.utc)


def _get_user(request: Request) -> dict:
    return getattr(request.state, 'user', {"id": "system", "email": "system", "role": "admin"})


def _create_creator_token(creator: dict) -> str:
    payload = {
        'sub': creator['id'],
        'email': creator['login_email'],
        'creator_id': creator['id'],
        'creator_name': creator.get('name', ''),
        'creator_code': creator.get('creator_code', ''),
        'aud': CREATOR_TOKEN_AUDIENCE,
        'exp': _now() + timedelta(hours=CREATOR_TOKEN_HOURS),
    }
    return pyjwt.encode(payload, JWT_SECRET, algorithm='HS256')


def _decode_creator_token(token: str) -> Optional[dict]:
    try:
        return pyjwt.decode(
            token, JWT_SECRET, algorithms=['HS256'], audience=CREATOR_TOKEN_AUDIENCE
        )
    except Exception:
        return None


async def require_creator_auth(request: Request) -> dict:
    """Require creator portal authentication."""
    auth = request.headers.get('Authorization', '')
    if not auth.startswith('Bearer '):
        raise HTTPException(401, 'Token tidak ditemukan')
    token = auth.split(' ', 1)[1]
    payload = _decode_creator_token(token)
    if not payload:
        raise HTTPException(401, 'Token tidak valid atau kadaluarsa')
    db = get_db()
    creator = await db.marketing_kol_creators.find_one({'id': payload.get('creator_id')}, {'_id': 0})
    if not creator or creator.get('status') != 'active':
        raise HTTPException(403, 'Akun creator tidak aktif')
    creator.pop('login_password_hash', None)
    return creator


def _client_ip(request: Request) -> str:
    fwd = request.headers.get('X-Forwarded-For')
    if fwd:
        return fwd.split(',')[0].strip()
    return getattr(request.client, 'host', 'unknown') if request.client else 'unknown'


async def _check_creator_lockout(db, identifier: str) -> None:
    """Raise 429 if identifier is locked out. Auto-clear if lockout expired."""
    doc = await db.marketing_kol_login_attempts.find_one({'identifier': identifier}, {'_id': 0})
    if not doc:
        return
    locked_until = doc.get('locked_until')
    if locked_until is None:
        return
    if locked_until.tzinfo is None:
        locked_until = locked_until.replace(tzinfo=timezone.utc)
    now = _now()
    if locked_until > now:
        remaining = int((locked_until - now).total_seconds() / 60) + 1
        raise HTTPException(429, f'Terlalu banyak percobaan login. Coba lagi dalam {remaining} menit.')
    await db.marketing_kol_login_attempts.delete_one({'identifier': identifier})


async def _record_failed_attempt(db, identifier: str) -> int:
    doc = await db.marketing_kol_login_attempts.find_one_and_update(
        {'identifier': identifier},
        {'$inc': {'attempts': 1}, '$set': {'last_attempt_at': _now()},
         '$setOnInsert': {'identifier': identifier, 'first_attempt_at': _now()}},
        upsert=True, return_document=True,
    )
    attempts = (doc or {}).get('attempts', 1)
    if attempts >= CREATOR_LOGIN_MAX_ATTEMPTS:
        locked_until = _now() + timedelta(minutes=CREATOR_LOGIN_LOCKOUT_MINUTES)
        await db.marketing_kol_login_attempts.update_one(
            {'identifier': identifier}, {'$set': {'locked_until': locked_until}}
        )
    return max(0, CREATOR_LOGIN_MAX_ATTEMPTS - attempts)


async def _clear_attempts(db, identifier: str) -> None:
    await db.marketing_kol_login_attempts.delete_one({'identifier': identifier})


# ── Pydantic models ──────────────────────────────────────────────────────────────

class CreatorCreate(BaseModel):
    name: str = Field(..., min_length=1)
    creator_code: str = Field(..., description="Unique code e.g. KOL-001")
    # SESI #34 — kreator tipe `new` BELUM punya akun portal: datanya diinput staf
    # marketing. Karena itu email/password menjadi OPSIONAL; tanpa keduanya,
    # kreator tetap tercatat tetapi TIDAK BISA login (dan layar mengatakannya).
    login_email: Optional[str] = Field(None, description="Creator login email (opsional untuk tipe 'new')")
    login_password: Optional[str] = Field(None, min_length=6)
    creator_type: str = Field("new", description="new | kontrak | continue")
    domicile: Optional[str] = Field(None, description="Domisili (kota/kabupaten)")
    domicile_detail: Optional[str] = None
    phone: Optional[str] = None
    platforms: Optional[dict] = Field(default_factory=dict)
    assigned_account_ids: Optional[List[str]] = Field(default_factory=list)
    kpi_targets: Optional[dict] = Field(default_factory=dict)
    notes: Optional[str] = None


class CreatorUpdate(BaseModel):
    name: Optional[str] = None
    creator_type: Optional[str] = Field(None, description="new | kontrak | continue")
    domicile: Optional[str] = None
    domicile_detail: Optional[str] = None
    login_email: Optional[str] = None
    phone: Optional[str] = None
    platforms: Optional[dict] = None
    assigned_account_ids: Optional[List[str]] = None
    kpi_targets: Optional[dict] = None
    notes: Optional[str] = None
    status: Optional[str] = Field(None, description="active | inactive")
    login_password: Optional[str] = Field(None, min_length=6)


class SessionCreate(BaseModel):
    creator_id: str
    account_id: str
    date: str = Field(..., description="YYYY-MM-DD")
    platform: str = Field(..., description="shopee | tiktokshop | tokopedia")
    session_name: Optional[str] = None
    duration_minutes: int = Field(0, ge=0)
    viewers: int = Field(0, ge=0)
    peak_viewers: int = Field(0, ge=0)
    revenue: float = Field(0, ge=0)
    orders: int = Field(0, ge=0)
    items_promoted: Optional[List[str]] = Field(default_factory=list)
    notes: Optional[str] = None


class ItemRequestCreate(BaseModel):
    account_id: str
    catalog_item_id: str
    quantity_requested: int = Field(..., ge=1)
    purpose: Optional[str] = None
    notes: Optional[str] = None


class CreatorPortalSessionCreate(BaseModel):
    # Creator self-report dari portal. creator_id diambil dari token (bukan body).
    account_id: str
    date: str = Field(..., description="YYYY-MM-DD")
    platform: str = Field("shopee", description="shopee | tiktokshop | tokopedia")
    session_name: Optional[str] = None
    duration_minutes: int = Field(0, ge=0)
    viewers: int = Field(0, ge=0)
    peak_viewers: int = Field(0, ge=0)
    revenue: float = Field(0, ge=0)
    orders: int = Field(0, ge=0)
    items_promoted: Optional[List[str]] = Field(default_factory=list)
    notes: Optional[str] = None


class CatalogItemCreate(BaseModel):
    account_id: str
    fg_product_id: str = Field(..., description="Material ID from rahaza_materials (type=fg)")
    product_name: str
    sku: str
    category: Optional[str] = None
    unit_price: float = Field(0, ge=0)
    description: Optional[str] = None
    is_active: bool = True


class CreatorLoginIn(BaseModel):
    email: str
    password: str
