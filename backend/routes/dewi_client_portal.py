"""
CV. Dewi Aditya — Phase 4: Maklon Client Portal
External authentication & read-mostly API for maklon clients.

Endpoints under: /api/dewi/client-portal/*
- Auth: separate JWT with audience 'maklon-client' so internal & client tokens never overlap.
- Every endpoint is scoped to the authenticated client_id.
- Clients can: view orders, view production timeline, view QC reports, approve/reject/revise samples,
  view invoices & payment status, view their profile.
"""
import logging
from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel, Field, EmailStr
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone, timedelta, date
from database import get_db
from auth import JWT_SECRET, hash_password, verify_password
from utils.data_quality import SkipTracker

logger = logging.getLogger(__name__)
from routes._maklon_adapter import po_to_legacy_order
import uuid
import jwt as pyjwt
import asyncio

# ══════════════════════════════════════════════════════════════════════════════
# BRUTE FORCE PROTECTION (Maklon Client Portal)
# ══════════════════════════════════════════════════════════════════════════════
_BF_MAX_ATTEMPTS = 5
_BF_LOCKOUT_MINUTES = 15

async def _client_check_brute_force(db, identifier: str):
    """Raise 429 if identifier is locked out."""
    doc = await db.client_login_attempts.find_one({"identifier": identifier}, {"_id": 0})
    if not doc:
        return
    locked_until = doc.get("locked_until")
    if locked_until:
        lu = locked_until if isinstance(locked_until, datetime) else datetime.fromisoformat(str(locked_until).replace("Z", "+00:00"))
        if lu.tzinfo is None:
            lu = lu.replace(tzinfo=timezone.utc)
        if lu > datetime.now(timezone.utc):
            remaining = int((lu - datetime.now(timezone.utc)).total_seconds() / 60) + 1
            raise HTTPException(429, f"Akun terkunci sementara karena terlalu banyak percobaan login. Coba lagi dalam {remaining} menit.")

async def _client_record_failed(db, identifier: str):
    """Record failed attempt; lock if >= max."""
    doc = await db.client_login_attempts.find_one({"identifier": identifier}, {"_id": 0})
    attempts = (doc.get("attempts", 0) if doc else 0) + 1
    update = {"$set": {
        "identifier": identifier,
        "attempts": attempts,
        "last_attempt": datetime.now(timezone.utc),
        "locked_until": (datetime.now(timezone.utc) + timedelta(minutes=_BF_LOCKOUT_MINUTES)) if attempts >= _BF_MAX_ATTEMPTS else None,
    }}
    await db.client_login_attempts.update_one({"identifier": identifier}, update, upsert=True)

async def _client_clear_attempts(db, identifier: str):
    """Clear failed attempts on successful login."""
    await db.client_login_attempts.delete_one({"identifier": identifier})

async def _ensure_client_bf_index(db):
    """Create TTL index on client_login_attempts. Called on startup."""
    try:
        await db.client_login_attempts.create_index("identifier")
        await db.client_login_attempts.create_index(
            "locked_until",
            expireAfterSeconds=int(_BF_LOCKOUT_MINUTES * 60 * 2),
            sparse=True
        )
    except Exception:
        logging.getLogger(__name__).debug("suppressed exception", exc_info=True)

router = APIRouter(prefix='/api/dewi/client-portal', tags=['Dewi-Client-Portal'])

CLIENT_TOKEN_AUDIENCE = 'maklon-client'
CLIENT_TOKEN_HOURS = 12

# ══════════════════════════════════════════════════════════════════════════════
# AUTH HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def _create_client_token(user: dict) -> str:
    payload = {
        'sub': user['id'],
        'email': user['email'],
        'client_id': user['client_id'],
        'client_name': user.get('client_name', ''),
        'aud': CLIENT_TOKEN_AUDIENCE,
        'exp': datetime.now(timezone.utc) + timedelta(hours=CLIENT_TOKEN_HOURS),
    }
    return pyjwt.encode(payload, JWT_SECRET, algorithm='HS256')


def _decode_client_token(token: str) -> Optional[dict]:
    try:
        return pyjwt.decode(
            token, JWT_SECRET, algorithms=['HS256'], audience=CLIENT_TOKEN_AUDIENCE
        )
    except Exception:
        return None


async def require_client_auth(request: Request) -> dict:
    """Dependency that loads the maklon client from a Bearer token."""
    auth = request.headers.get('Authorization', '')
    if not auth.startswith('Bearer '):
        raise HTTPException(401, 'Token tidak ditemukan')
    token = auth.split(' ', 1)[1]
    payload = _decode_client_token(token)
    if not payload:
        raise HTTPException(401, 'Token tidak valid atau kadaluarsa')
    db = get_db()
    user = await db.dewi_client_users.find_one({'id': payload.get('sub')})
    if not user or user.get('status') != 'active':
        raise HTTPException(403, 'Akun klien tidak aktif')
    user.pop('_id', None)
    user.pop('password', None)
    # Force password change before any non-/auth route is reachable
    if user.get('must_change_password'):
        path = request.url.path or ''
        if not path.startswith('/api/dewi/client-portal/auth/'):
            raise HTTPException(
                status_code=428,
                detail='Anda wajib mengganti password terlebih dahulu',
            )
    return user


def _clean(doc: Optional[dict]) -> Optional[dict]:
    if not doc:
        return doc
    doc.pop('_id', None)
    return doc


# ══════════════════════════════════════════════════════════════════════════════
# AUTH ROUTES
# ══════════════════════════════════════════════════════════════════════════════

class ClientLoginIn(BaseModel):
    email: EmailStr
    password: str


class ChangePasswordIn(BaseModel):
    old_password: str
    new_password: str = Field(..., min_length=6)


@router.post('/auth/login')
async def client_login(payload: ClientLoginIn, request: Request):
    db = get_db()

    # Brute-force protection
    forwarded_for = request.headers.get("X-Forwarded-For", "")
    client_ip = forwarded_for.split(",")[0].strip() if forwarded_for else getattr(request.client, "host", "unknown")
    bf_key = f"client:{client_ip}:{payload.email.lower().strip()}"

    await _client_check_brute_force(db, bf_key)

    user = await db.dewi_client_users.find_one({'email': payload.email.lower().strip()})
    if not user or not verify_password(payload.password, user.get('password', '')):
        await _client_record_failed(db, bf_key)
        doc = await db.client_login_attempts.find_one({"identifier": bf_key}, {"_id": 0})
        attempts_left = max(0, _BF_MAX_ATTEMPTS - (doc.get("attempts", 0) if doc else 0))
        raise HTTPException(401, f'Email atau password salah. {f"Tersisa {attempts_left} percobaan." if attempts_left > 0 else "Akun terkunci 15 menit."}')
    if user.get('status') != 'active':
        raise HTTPException(403, 'Akun belum aktif. Hubungi admin CV. Dewi Aditya.')

    # Refresh client_name snapshot
    client = await db.dewi_maklon_clients.find_one({'id': user.get('client_id')})
    client_name = client.get('name') if client else user.get('client_name', '')

    now = datetime.now(timezone.utc)
    await db.dewi_client_users.update_one(
        {'id': user['id']},
        {'$set': {'last_login_at': now, 'client_name': client_name}},
    )

    user_payload = {
        'id': user['id'],
        'email': user['email'],
        'client_id': user['client_id'],
        'client_name': client_name,
    }
    token = _create_client_token(user_payload)

    # Clear failed attempts on successful login
    await _client_clear_attempts(db, bf_key)

    return {
        'token': token,
        'expires_in_hours': CLIENT_TOKEN_HOURS,
        'user': {
            'id': user['id'],
            'email': user['email'],
            'name': user.get('name') or client_name,
            'client_id': user['client_id'],
            'client_name': client_name,
            'must_change_password': bool(user.get('must_change_password')),
        },
    }


@router.get('/auth/me')
async def client_me(client: dict = Depends(require_client_auth)):
    db = get_db()
    cl = await db.dewi_maklon_clients.find_one({'id': client.get('client_id')})
    cl = _clean(cl)
    return {
        'user': {
            'id': client.get('id'),
            'email': client.get('email'),
            'name': client.get('name') or (cl or {}).get('name', ''),
            'client_id': client.get('client_id'),
            'must_change_password': bool(client.get('must_change_password')),
            'last_login_at': client.get('last_login_at'),
        },
        'client': cl,
    }


@router.post('/auth/change-password')
async def client_change_password(payload: ChangePasswordIn, client: dict = Depends(require_client_auth)):
    db = get_db()
    user = await db.dewi_client_users.find_one({'id': client.get('id')})
    if not user or not verify_password(payload.old_password, user.get('password', '')):
        raise HTTPException(400, 'Password lama salah')
    if payload.old_password == payload.new_password:
        raise HTTPException(400, 'Password baru harus berbeda dari yang lama')
    await db.dewi_client_users.update_one(
        {'id': user['id']},
        {'$set': {
            'password': hash_password(payload.new_password),
            'must_change_password': False,
            'updated_at': datetime.now(timezone.utc),
        }},
    )
    return {'message': 'Password berhasil diubah'}


# ══════════════════════════════════════════════════════════════════════════════
# DASHBOARD
# ══════════════════════════════════════════════════════════════════════════════

@router.get('/dashboard')
async def client_dashboard(client: dict = Depends(require_client_auth)):
    db = get_db()
    cid = client.get('client_id')

    # P1.B: SSOT is dewi_maklon_pos (legacy dewi_maklon_orders deprecated)
    total_orders = await db.dewi_maklon_pos.count_documents({'client_id': cid})
    active_orders = await db.dewi_maklon_pos.count_documents({
        'client_id': cid,
        'status': {'$nin': ['draft', 'completed', 'cancelled', 'invoiced']},
    })
    completed_orders = await db.dewi_maklon_pos.count_documents({
        'client_id': cid, 'status': {'$in': ['completed', 'invoiced']},
    })

    # Samples pending client action
    pending_samples = await db.dewi_maklon_samples.count_documents({
        'client_id': cid, 'status': {'$in': ['submitted', 'revision_requested']},
    })

    # Invoices outstanding
    outstanding_invoices = await db.dewi_maklon_invoices.find({
        'client_id': cid,
        'status': {'$in': ['issued', 'partial_paid', 'overdue']},
        'balance_amount': {'$gt': 0},
    }).to_list(length=200)
    total_outstanding = round(sum(float(i.get('balance_amount', 0) or 0) for i in outstanding_invoices), 2)
    today = datetime.now(timezone.utc).date()
    overdue_count = 0
    # 2026-08-07 — DULU invoice yang tanggalnya rusak di-`continue` DIAM-DIAM di
    # PORTAL KLIEN. Efeknya klien melihat "0 tagihan terlambat" padahal ada; ini
    # angka yang dilihat pihak LUAR perusahaan, jadi paling tidak boleh menyesatkan.
    dq_inv = SkipTracker("tagihan portal klien")
    for i in outstanding_invoices:
        try:
            d = date.fromisoformat(i.get('due_date') or '2099-12-31')
            if d < today:
                overdue_count += 1
        except (ValueError, TypeError) as e:
            dq_inv.skip(doc_id=i.get('id'), label=i.get('invoice_number'),
                        field='due_date', value=i.get('due_date'), error=e)
            continue
    dq_inv.log(logger)

    # Recent orders (last 5) — read from dewi_maklon_pos, project to legacy order shape
    recent_pos = await db.dewi_maklon_pos.find(
        {'client_id': cid}
    ).sort('po_date', -1).to_list(length=5)
    recent_orders = [po_to_legacy_order(_clean(p)) for p in recent_pos]

    # Pending action samples (full info, last 5)
    pending_sample_list = await db.dewi_maklon_samples.find({
        'client_id': cid,
        'status': {'$in': ['submitted', 'revision_requested']},
    }).sort('updated_at', -1).to_list(length=5)

    return {
        'orders': {
            'total': total_orders,
            'active': active_orders,
            'completed': completed_orders,
        },
        'samples': {
            'pending_approval': pending_samples,
        },
        'invoices': {
            'outstanding_count': len(outstanding_invoices),
            'outstanding_amount': total_outstanding,
            'overdue_count': overdue_count,
        },
        'recent_orders': recent_orders,
        'pending_samples': [_clean(s) for s in pending_sample_list],
    }


# ══════════════════════════════════════════════════════════════════════════════
# ORDERS
# ══════════════════════════════════════════════════════════════════════════════

ORDER_TIMELINE_STAGES = [
    'draft', 'confirmed', 'material_ready', 'cutting', 'sewing', 'qc',
    'packing', 'completed', 'invoiced',
]


def _build_timeline(order: dict) -> List[dict]:
    """Build a stage timeline of where the order is."""
    current = order.get('status', 'draft')
    try:
        idx = ORDER_TIMELINE_STAGES.index(current)
    except ValueError:
        idx = -1
    timeline = []
    for i, stage in enumerate(ORDER_TIMELINE_STAGES):
        if stage == 'draft':
            continue
        state = 'completed' if i < idx else ('current' if i == idx else 'upcoming')
        if current == 'cancelled':
            state = 'cancelled'
        timeline.append({'stage': stage, 'state': state})
    return timeline


@router.get('/orders')
async def client_list_orders(
    status: Optional[str] = None,
    client: dict = Depends(require_client_auth),
):
    db = get_db()
    # P1.B: read from dewi_maklon_pos SSOT, project to legacy order shape
    query: Dict[str, Any] = {'client_id': client.get('client_id')}
    if status:
        # Caller may pass either legacy ('cutting','sewing','qc','packing','material_ready')
        # or new PO status. Use LEGACY_TO_PO_STATUS to translate when caller uses legacy.
        from routes._maklon_adapter import LEGACY_TO_PO_STATUS
        po_status = LEGACY_TO_PO_STATUS.get(status, status)
        query['status'] = po_status
    pos = await db.dewi_maklon_pos.find(query).sort('po_date', -1).to_list(length=500)
    orders = [po_to_legacy_order(_clean(p)) for p in pos]
    # If caller asked for a specific legacy status, fine-filter the projected list
    if status and status in ('cutting', 'sewing', 'qc', 'packing', 'material_ready'):
        orders = [o for o in orders if o.get('status') == status]
    return orders


@router.get('/orders/{order_id}')
async def client_get_order(order_id: str, client: dict = Depends(require_client_auth)):
    db = get_db()
    # P1.B: read from dewi_maklon_pos SSOT
    po = await db.dewi_maklon_pos.find_one({
        'id': order_id, 'client_id': client.get('client_id'),
    })
    if not po:
        raise HTTPException(404, 'Order tidak ditemukan')
    order = po_to_legacy_order(_clean(po))
    # Counts of related objects
    order['samples_count'] = await db.dewi_maklon_samples.count_documents({
        '$or': [{'order_id': order_id}, {'po_id': order_id}],
        'client_id': client.get('client_id'),
    })
    order['qc_count'] = await db.dewi_maklon_qc_checks.count_documents({
        '$or': [{'order_id': order_id}, {'po_id': order_id}],
    })
    order['timeline'] = _build_timeline(order)
    return order


@router.get('/orders/{order_id}/qc')
async def client_order_qc(order_id: str, client: dict = Depends(require_client_auth)):
    db = get_db()
    po = await db.dewi_maklon_pos.find_one({
        'id': order_id, 'client_id': client.get('client_id'),
    })
    if not po:
        raise HTTPException(404, 'Order tidak ditemukan')
    checks = await db.dewi_maklon_qc_checks.find(
        {'$or': [{'order_id': order_id}, {'po_id': order_id}]}
    ).sort('created_at', -1).to_list(length=500)
    return [_clean(c) for c in checks]


@router.get('/orders/{order_id}/samples')
async def client_order_samples(order_id: str, client: dict = Depends(require_client_auth)):
    db = get_db()
    # Ownership check (read from SSOT)
    po = await db.dewi_maklon_pos.find_one({
        'id': order_id, 'client_id': client.get('client_id'),
    })
    if not po:
        raise HTTPException(404, 'Order tidak ditemukan')
    samples = await db.dewi_maklon_samples.find(
        {'$or': [{'order_id': order_id}, {'po_id': order_id}],
         'client_id': client.get('client_id')}
    ).sort('created_at', -1).to_list(length=200)
    return [_clean(s) for s in samples]


# ══════════════════════════════════════════════════════════════════════════════
# SAMPLES
# ══════════════════════════════════════════════════════════════════════════════

class SampleApprovalIn(BaseModel):
    feedback: Optional[str] = None


class SampleRejectIn(BaseModel):
    reason: str
    changes_required: Optional[str] = None


class SampleRevisionIn(BaseModel):
    reason: str
    changes_required: Optional[str] = None
    photos: List[str] = Field(default_factory=list)


@router.get('/samples')
async def client_list_samples(
    status: Optional[str] = None,
    client: dict = Depends(require_client_auth),
):
    db = get_db()
    query: Dict[str, Any] = {'client_id': client.get('client_id')}
    if status:
        query['status'] = status
    samples = await db.dewi_maklon_samples.find(query).sort('created_at', -1).to_list(length=500)
    return [_clean(s) for s in samples]


@router.get('/samples/{sample_id}')
async def client_get_sample(sample_id: str, client: dict = Depends(require_client_auth)):
    db = get_db()
    sample = await db.dewi_maklon_samples.find_one({
        'id': sample_id, 'client_id': client.get('client_id'),
    })
    if not sample:
        raise HTTPException(404, 'Sample tidak ditemukan')
    revisions = await db.dewi_maklon_sample_revisions.find(
        {'sample_id': sample_id}
    ).sort('created_at', -1).to_list(length=100)
    sample = _clean(sample)
    sample['revisions'] = [_clean(r) for r in revisions]
    return sample


async def _ensure_sample_actionable(db, sample_id: str, client_id: str) -> dict:
    sample = await db.dewi_maklon_samples.find_one({'id': sample_id, 'client_id': client_id}, {'_id': 0})
    if not sample:
        raise HTTPException(404, 'Sample tidak ditemukan')
    if sample.get('status') not in ['submitted', 'revision_requested']:
        raise HTTPException(400, 'Sample belum siap untuk action klien')
    return sample


@router.post('/samples/{sample_id}/approve')
async def client_approve_sample(
    sample_id: str,
    payload: SampleApprovalIn,
    client: dict = Depends(require_client_auth),
):
    db = get_db()
    cid = client.get('client_id')
    await _ensure_sample_actionable(db, sample_id, cid)
    now = datetime.now(timezone.utc)
    await db.dewi_maklon_samples.update_one(
        {'id': sample_id},
        {'$set': {
            'status': 'approved',
            'approved_by_name': client.get('client_name') or client.get('email'),
            'approved_at': now,
            'approval_feedback': payload.feedback,
            'updated_at': now,
        }},
    )
    return {'message': 'Sample disetujui'}


@router.post('/samples/{sample_id}/reject')
async def client_reject_sample(
    sample_id: str,
    payload: SampleRejectIn,
    client: dict = Depends(require_client_auth),
):
    db = get_db()
    cid = client.get('client_id')
    await _ensure_sample_actionable(db, sample_id, cid)
    now = datetime.now(timezone.utc)
    await db.dewi_maklon_samples.update_one(
        {'id': sample_id},
        {'$set': {
            'status': 'rejected',
            'rejected_by_name': client.get('client_name') or client.get('email'),
            'rejected_at': now,
            'rejection_reason': payload.reason,
            'rejection_changes_required': payload.changes_required,
            'updated_at': now,
        }},
    )
    return {'message': 'Sample ditolak'}


@router.post('/samples/{sample_id}/revision')
async def client_request_revision(
    sample_id: str,
    payload: SampleRevisionIn,
    client: dict = Depends(require_client_auth),
):
    db = get_db()
    cid = client.get('client_id')
    sample = await _ensure_sample_actionable(db, sample_id, cid)
    now = datetime.now(timezone.utc)
    new_rev = int(sample.get('revision_number', 0)) + 1
    await db.dewi_maklon_sample_revisions.insert_one({
        'id': str(uuid.uuid4()),
        'sample_id': sample_id,
        'revision_number': new_rev,
        'reason': payload.reason,
        'changes_required': payload.changes_required,
        'photos': payload.photos,
        'requested_by': client.get('client_name') or client.get('email'),
        'requested_by_role': 'client',
        'created_at': now,
    })
    await db.dewi_maklon_samples.update_one(
        {'id': sample_id},
        {'$set': {
            'status': 'revision_requested',
            'revision_number': new_rev,
            'updated_at': now,
        }},
    )
    return {'message': f'Revisi #{new_rev} diajukan', 'revision_number': new_rev}


# ══════════════════════════════════════════════════════════════════════════════
# INVOICES
# ══════════════════════════════════════════════════════════════════════════════

@router.get('/invoices')
async def client_list_invoices(
    status: Optional[str] = None,
    client: dict = Depends(require_client_auth),
):
    db = get_db()
    query: Dict[str, Any] = {'client_id': client.get('client_id')}
    if status:
        query['status'] = status
    invoices = await db.dewi_maklon_invoices.find(query).sort('issue_date', -1).to_list(length=500)
    return [_clean(i) for i in invoices]


@router.get('/invoices/{invoice_id}')
async def client_get_invoice(invoice_id: str, client: dict = Depends(require_client_auth)):
    db = get_db()
    inv = await db.dewi_maklon_invoices.find_one({
        'id': invoice_id, 'client_id': client.get('client_id'),
    })
    if not inv:
        raise HTTPException(404, 'Invoice tidak ditemukan')
    payments = await db.dewi_maklon_payments.find(
        {'invoice_id': invoice_id}
    ).sort('payment_date', -1).to_list(length=100)
    inv = _clean(inv)
    inv['payments'] = [_clean(p) for p in payments]
    return inv


@router.get('/invoices/{invoice_id}/pdf')
async def client_invoice_pdf(invoice_id: str, client: dict = Depends(require_client_auth)):
    """Download invoice PDF (scoped to authenticated client)."""
    from fastapi.responses import Response
    from utils.invoice_pdf import build_invoice_pdf
    db = get_db()
    inv = await db.dewi_maklon_invoices.find_one({
        'id': invoice_id, 'client_id': client.get('client_id'),
    })
    if not inv:
        raise HTTPException(404, 'Invoice tidak ditemukan')
    cl = await db.dewi_maklon_clients.find_one({'id': client.get('client_id')}) or {}
    co = await db.company_settings.find_one({}) or {}
    # SESI #19 — kop/kolom/tanda tangan/footer invoice mengikuti TEMPLATE PDF pemilik
    # (layar "PDF & Kop Surat"). Tanpa ini invoice tetap memakai kop tanam kode
    # tanpa logo/NPWP sementara dokumen lain sudah mengikuti setelan.
    from utils.pdf_common import get_company_profile, get_doc_settings
    _ds = await get_doc_settings(db, 'invoice-maklon')
    pdf = build_invoice_pdf(invoice=inv, client=cl, company=co,
                            template=(_ds or {}).get('_template'),
                            profile=await get_company_profile(db))
    return Response(
        content=pdf,
        media_type='application/pdf',
        headers={
            'Content-Disposition': f'inline; filename="Invoice_{inv.get("invoice_number")}.pdf"',
        },
    )


# ══════════════════════════════════════════════════════════════════════════════
# PROFILE
# ══════════════════════════════════════════════════════════════════════════════

@router.get('/profile')
async def client_profile(client: dict = Depends(require_client_auth)):
    db = get_db()
    cl = await db.dewi_maklon_clients.find_one({'id': client.get('client_id')})
    if not cl:
        raise HTTPException(404, 'Profil klien tidak ditemukan')
    return _clean(cl)



# ──────────────────────────────────────────────────────────────────────────────
# BADGE COUNTS  (for nav badges in client portal shell)
# ──────────────────────────────────────────────────────────────────────────────

@router.get('/badge-counts')
async def client_badge_counts(client: dict = Depends(require_client_auth)):
    """
    Returns fast badge counts for client portal nav items.
    Samples badge = samples awaiting client approval (submitted / revision_requested).
    Invoices badge = unpaid / overdue invoices.
    """
    db = get_db()
    cid = client.get('client_id')

    pending_samples, outstanding_invoices = await asyncio.gather(
        db.dewi_maklon_samples.count_documents({
            'client_id': cid, 'status': {'$in': ['submitted', 'revision_requested']},
        }),
        db.dewi_maklon_invoices.count_documents({
            'client_id': cid,
            'status': {'$in': ['issued', 'partial_paid', 'overdue']},
            'balance_amount': {'$gt': 0},
        }),
    )
    return {
        'samples': pending_samples,
        'invoices': outstanding_invoices,
    }
