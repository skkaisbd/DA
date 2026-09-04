"""
Authentication Routes
Extracted from server.py monolith.
"""
from fastapi import APIRouter, Request, HTTPException
from database import get_db
from auth import (require_auth, verify_password,
                  create_token, log_activity, serialize_doc)
from routes.shared import get_user_portals
import logging
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["auth"])

# ─── BRUTE FORCE PROTECTION ──────────────────────────────────────────────────
# Layer 1: per-IP+email — 5 attempts / 15 min (guards per-device)
# Layer 2: per-email only — 20 total attempts / 60 min (guards against distributed attack)
MAX_ATTEMPTS_IP    = 5
LOCKOUT_MIN_IP     = 15
MAX_ATTEMPTS_EMAIL = 20
LOCKOUT_MIN_EMAIL  = 60

async def _check_brute_force(db, identifier: str):
    """Check if the identifier is locked out. Raises 429 if locked."""
    doc = await db.login_attempts.find_one({"identifier": identifier}, {"_id": 0})
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

async def _record_failed_attempt(db, identifier: str, max_attempts: int, lockout_minutes: int):
    """Increment failed attempts. Lock if >= max_attempts."""
    doc = await db.login_attempts.find_one({"identifier": identifier}, {"_id": 0})
    attempts = (doc.get("attempts", 0) if doc else 0) + 1
    locked_until = (datetime.now(timezone.utc) + timedelta(minutes=lockout_minutes)) if attempts >= max_attempts else None
    update = {"$set": {
        "identifier": identifier,
        "attempts": attempts,
        "last_attempt": datetime.now(timezone.utc),
        "locked_until": locked_until,
    }}
    await db.login_attempts.update_one({"identifier": identifier}, update, upsert=True)
    return attempts

async def _clear_attempts(db, *identifiers: str):
    """Clear failed attempts on successful login."""
    for ident in identifiers:
        await db.login_attempts.delete_one({"identifier": ident})

async def _ensure_brute_force_index(db):
    """Create TTL index on login_attempts. Call on startup."""
    try:
        await db.login_attempts.create_index("identifier", unique=True)
        await db.login_attempts.create_index(
            "locked_until",
            expireAfterSeconds=int(LOCKOUT_MIN_EMAIL * 60 * 2),
            sparse=True
        )
        await db.login_attempts.create_index(
            "last_attempt",
            expireAfterSeconds=int(LOCKOUT_MIN_EMAIL * 60 * 4),
            sparse=True
        )
    except Exception:
        logging.getLogger(__name__).debug("suppressed exception", exc_info=True)

# ─── AUTH ────────────────────────────────────────────────────────────────────
@router.post("/auth/login")
async def login(request: Request):
    body = await request.json()
    db = get_db()

    email = body.get('email', '').strip().lower()
    password = body.get('password', '')

    # Get real IP (behind proxy/k8s)
    forwarded_for = request.headers.get("X-Forwarded-For", "")
    client_ip = forwarded_for.split(",")[0].strip() if forwarded_for else getattr(request.client, "host", "unknown")
    bf_key_ip    = f"{client_ip}:{email}"   # Layer 1: per-IP+email
    bf_key_email = f"email:{email}"          # Layer 2: per-email only (distributed attack guard)

    # Check BOTH lockout layers BEFORE querying user (prevents user enumeration timing attacks)
    await _check_brute_force(db, bf_key_ip)
    await _check_brute_force(db, bf_key_email)

    u = await db.users.find_one({'email': email})
    if not u or not verify_password(password, u['password']):
        # Record failed attempt on BOTH layers
        await _record_failed_attempt(db, bf_key_ip,    MAX_ATTEMPTS_IP,    LOCKOUT_MIN_IP)
        await _record_failed_attempt(db, bf_key_email, MAX_ATTEMPTS_EMAIL, LOCKOUT_MIN_EMAIL)
        doc_ip = await db.login_attempts.find_one({"identifier": bf_key_ip}, {"_id": 0})
        attempts_left = max(0, MAX_ATTEMPTS_IP - (doc_ip.get("attempts", 0) if doc_ip else 0))
        raise HTTPException(401, f'Email atau password salah. {f"Tersisa {attempts_left} percobaan." if attempts_left > 0 else "Akun terkunci 15 menit."}')

    if u.get('status') != 'active' and not u.get('active', True):
        raise HTTPException(403, 'Akun tidak aktif')

    # Blokir akun yang dinonaktifkan eksplisit (mis. akun vendor CMT is_active=False).
    # Aman untuk akun lama: hanya mem-block bila is_active BENAR-BENAR False.
    if u.get('is_active') is False:
        raise HTTPException(403, 'Akun tidak aktif. Hubungi admin.')

    # Clear failed attempts on success (both layers)
    await _clear_attempts(db, bf_key_ip, bf_key_email)

    # Get user permissions for immediate use (without /auth/me call)
    user_perms = []
    role = u.get('role', '')
    if role == 'superadmin':
        user_perms = ['*']
    elif role == 'vendor':
        user_perms = ['dashboard.view', 'shipment.view', 'jobs.view', 'jobs.create', 'progress.view', 'progress.create']
    elif role == 'buyer':
        user_perms = ['dashboard.view', 'po.view', 'shipment.view']
    else:
        # Check custom role
        if u.get('role_id'):
            role_perms = await db.role_permissions.find({'role_id': u['role_id']}, {'_id': 0}).to_list(500)
            user_perms = [rp.get('permission_key') for rp in role_perms]
        else:
            custom_role = await db.roles.find_one({'name': role})
            if custom_role:
                role_perms = await db.role_permissions.find({'role_id': custom_role['id']}, {'_id': 0}).to_list(500)
                user_perms = [rp.get('permission_key') for rp in role_perms]

    token = create_token(u)
    await log_activity(u['id'], u['name'], 'Login', 'Auth', f"User {u['email']} logged in")
    # 2026-08-08 — `last_login_at` dicatat. Dipakai Portal CMT Override untuk
    # memperingatkan "vendor ini punya akun aktif, terakhir login <tanggal> —
    # hati-hati dobel input" (keputusan owner 5a). Tanpa jejak ini, peringatannya
    # hanya bisa menebak. Gagalnya pencatatan TIDAK BOLEH menggagalkan login.
    try:
        from datetime import datetime as _dt, timezone as _tz
        await db.users.update_one(
            {'id': u['id']},
            {'$set': {'last_login_at': _dt.now(_tz.utc)}})
    except Exception as _e:  # noqa: BLE001
        logger.warning("[auth] gagal mencatat last_login_at untuk %s: %s", u.get('email'), _e)
    # 2026-08-05 — akses efektif (portal + menu tersembunyi) langsung dikirim saat
    # login supaya UI tidak perlu panggilan kedua. SSOT: shared.resolve_role_access.
    _portals, _hidden = get_user_portals(u), []
    try:
        from routes.shared import resolve_role_access
        _acc = await resolve_role_access(db, {'id': u['id'], 'role': role})
        _portals, _hidden = _acc['portals'], _acc['hidden_modules']
        if _acc['extra_permissions'] and '*' not in user_perms:
            user_perms = sorted(set(user_perms) | set(_acc['extra_permissions']))
    except Exception as e:  # noqa: BLE001 — login TIDAK BOLEH gagal karena RBAC.
        # Fallback ke portal bawaan `get_user_portals`. 2026-08-07: dulu `pass`
        # senyap, sehingga bila resolusi izin gagal, pengguna diam-diam masuk
        # dengan akses BAWAAN (bukan yang diatur owner) dan tidak ada satu pun
        # jejak yang menjelaskan kenapa menunya berbeda.
        logger.warning(
            "[auth] resolusi akses role GAGAL untuk %s (role=%s) — memakai portal "
            "bawaan, konfigurasi izin owner TIDAK diterapkan pada sesi ini: %s",
            u.get('email'), role, e)
    return {'token': token, 'user': {'id': u['id'], 'name': u['name'], 'email': u['email'], 'role': u['role'],
            'vendor_id': u.get('vendor_id'), 'buyer_id': u.get('buyer_id'),
            'customer_name': u.get('customer_name', u.get('buyer_company', '')),
            'permissions': user_perms, 'hidden_modules': _hidden},
            'portals': _portals, 'hidden_modules': _hidden}

@router.get("/auth/me")
async def auth_me(request: Request):
    user = await require_auth(request)
    db = get_db()
    u = await db.users.find_one({'id': user['id']}, {'password': 0, '_id': 0})
    # Include user permissions for RBAC
    user_perms = []
    role = u.get('role', '') if u else ''
    
    if role == 'superadmin':
        user_perms = ['*']  # Full access
    elif role == 'vendor':
        user_perms = ['dashboard.view', 'shipment.view', 'jobs.view', 'jobs.create', 'progress.view', 'progress.create']
    elif role == 'buyer':
        user_perms = ['dashboard.view', 'po.view', 'shipment.view']
    else:
        # Check if this is a custom role
        if u.get('role_id'):
            # User has custom role assigned via role_id
            role_perms = await db.role_permissions.find({'role_id': u['role_id']}, {'_id': 0}).to_list(500)
            user_perms = [rp.get('permission_key') for rp in role_perms]
        else:
            # Try to find role by name (legacy)
            custom_role = await db.roles.find_one({'name': role})
            if custom_role:
                role_perms = await db.role_permissions.find({'role_id': custom_role['id']}, {'_id': 0}).to_list(500)
                user_perms = [rp.get('permission_key') for rp in role_perms]
    
    result = serialize_doc(u) if u else {}
    result['permissions'] = user_perms
    # 2026-08-05 — akses efektif (portal + menu tersembunyi + izin tambahan per
    # user) diselesaikan SATU tempat: routes/shared.resolve_role_access.
    try:
        from routes.shared import resolve_role_access
        access = await resolve_role_access(db, {'id': user['id'], 'role': role})
        result['portals'] = access['portals']
        result['hidden_modules'] = access['hidden_modules']
        result['is_super'] = access['is_super']
        if access['extra_permissions'] and '*' not in user_perms:
            result['permissions'] = sorted(set(user_perms) | set(access['extra_permissions']))
    except Exception:  # noqa: BLE001 — jangan sampai /auth/me gagal karena RBAC
        result['portals'] = get_user_portals({"role": role})
        result['hidden_modules'] = []
    return result


# ─── USERS LISTING (for dropdowns, assignment, etc) ──────────────────────────
@router.get("/auth/users")
async def list_users_for_assignment(request: Request):
    """List users for assignment dropdowns (task assignment, etc).
    
    Query params:
      - role: Filter by role (single role or comma-separated list)
      - roles: Alias for role
      - portal: Filter users who have access to specific portal (e.g., 'toko' for marketing)
      - status: Default 'active'. Use 'all' to include inactive.
      - search: Search by name or email
      - limit: Default 500
    
    Returns: List of {id, name, email, role, status, portals}
    Access: Any authenticated user (no admin-only restriction since used for assignment).
    """
    user = await require_auth(request)
    _ = user  # ensure require_auth was called for permission gate
    db = get_db()
    
    qp = request.query_params
    role_filter = qp.get('role') or qp.get('roles') or ''
    portal_filter = qp.get('portal') or ''
    status_filter = qp.get('status', 'active')
    search = (qp.get('search') or '').strip()
    try:
        limit = max(1, min(2000, int(qp.get('limit', 500))))
    except Exception:
        limit = 500
    
    query = {}
    # Status filter
    if status_filter != 'all':
        query['$or'] = [
            {'status': status_filter},
            {'active': True if status_filter == 'active' else False}
        ]
    
    # Role filter (supports comma-separated multi-role)
    if role_filter:
        roles = [r.strip() for r in role_filter.split(',') if r.strip()]
        if roles:
            query['role'] = {'$in': roles}
    
    # Search filter
    if search:
        search_or = [
            {'name': {'$regex': search, '$options': 'i'}},
            {'email': {'$regex': search, '$options': 'i'}},
        ]
        if '$or' in query:
            query = {'$and': [{'$or': query.pop('$or')}, {'$or': search_or}]}
        else:
            query['$or'] = search_or
    
    users = await db.users.find(
        query,
        {'_id': 0, 'password': 0, 'role_permissions_cache': 0}
    ).sort('name', 1).limit(limit).to_list(length=limit)
    
    # Portal filter (apply after fetch since portal is computed)
    if portal_filter:
        users = [
            u for u in users
            if portal_filter in (get_user_portals({"role": u.get('role', '')}) or [])
        ]
    
    # Strip sensitive fields, attach portals
    result = []
    for u in users:
        result.append({
            'id': u.get('id'),
            'name': u.get('name', u.get('email', '')),
            'email': u.get('email'),
            'role': u.get('role'),
            'status': u.get('status') or ('active' if u.get('active', True) else 'inactive'),
            'portals': get_user_portals({"role": u.get('role', '')}),
        })
    
    return result

