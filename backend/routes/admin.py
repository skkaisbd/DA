"""
Admin: Users, Activity Logs, Company Settings, RBAC
Extracted from server.py monolith.
"""
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse
from database import get_db
from auth import (require_auth, check_role, hash_password, serialize_doc,
                  bump_rbac_cache)
from routes.shared import new_id, now
from routes.rahaza_audit import log_audit
from data.permission_catalog import (
    flat_permissions, grouped_permissions, all_permission_keys, validate_keys,
)
import logging
from utils.query_guards import q_int

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["admin"])

# ─── USERS ───────────────────────────────────────────────────────────────────
@router.get("/users")
async def get_users(request: Request):
    user = await require_auth(request)
    if not check_role(user, ['admin']):
        raise HTTPException(403, 'Forbidden')
    db = get_db()
    return serialize_doc(await db.users.find({}, {'password': 0, '_id': 0}).sort('created_at', -1).to_list(500))

@router.post("/users")
async def create_user(request: Request):
    user = await require_auth(request)
    if user.get('role') != 'superadmin':
        raise HTTPException(403, 'Forbidden')
    db = get_db()
    body = await request.json()
    email = (body.get('email') or '').strip().lower()
    if not email:
        raise HTTPException(400, 'Email wajib diisi.')
    existing = await db.users.find_one({'email': email}, {'_id': 0, 'id': 1})
    if existing:
        raise HTTPException(409, f"Email '{email}' sudah terdaftar.")
    hashed = hash_password(body.get('password', 'User@123'))
    new_user = {'id': new_id(), **body, 'email': email, 'password': hashed, 'status': 'active', 'created_at': now(), 'updated_at': now()}
    try:
        await db.users.insert_one(new_user)
    except Exception as e:
        if 'duplicate key' in str(e).lower() or 'E11000' in str(e):
            raise HTTPException(409, f"Email '{email}' sudah terdaftar.")
        raise HTTPException(500, f"Gagal membuat user: {e}")
    result = {k: v for k, v in new_user.items() if k != 'password'}
    return JSONResponse(serialize_doc(result), status_code=201)

@router.put("/users/{uid}")
async def update_user(uid: str, request: Request):
    user = await require_auth(request)
    if user.get('role') != 'superadmin':
        raise HTTPException(403, 'Forbidden')
    db = get_db()
    body = await request.json()
    body.pop('_id', None)
    body.pop('id', None)
    if body.get('password'):
        body['password'] = hash_password(body['password'])
    await db.users.update_one({'id': uid}, {'$set': {**body, 'updated_at': now()}})
    bump_rbac_cache()
    return serialize_doc(await db.users.find_one({'id': uid}, {'password': 0, '_id': 0}))

@router.delete("/users/{uid}")
async def delete_user(uid: str, request: Request):
    user = await require_auth(request)
    if user.get('role') != 'superadmin':
        raise HTTPException(403, 'Forbidden')
    db = get_db()
    doc = await db.users.find_one({'id': uid})
    if not doc:
        raise HTTPException(404, 'Not found')
    if doc.get('role') == 'superadmin':
        raise HTTPException(403, 'Cannot delete superadmin')
    if doc['id'] == user['id']:
        raise HTTPException(403, 'Cannot delete own account')
    await db.users.delete_one({'id': uid})
    return {'success': True}


# ─── ACTIVITY LOGS ───────────────────────────────────────────────────────────
@router.get("/activity-logs")
async def get_activity_logs(request: Request):
    user = await require_auth(request)
    if not check_role(user, ['admin']):
        raise HTTPException(403, 'Forbidden')
    db = get_db()
    sp = request.query_params
    query = {}
    if sp.get('module'):
        query['module'] = sp['module']
    if sp.get('user_id'):
        query['user_id'] = sp['user_id']  # NEW: filter by user
    limit = q_int(sp.get('limit'), default=100, name='limit', minimum=1, maximum=500)
    return serialize_doc(await db.activity_logs.find(query, {'_id': 0}).sort('timestamp', -1).limit(limit).to_list(500))

@router.delete("/activity-logs/{log_id}")
async def delete_activity_log(log_id: str, request: Request):
    user = await require_auth(request)
    if user.get('role') != 'superadmin':
        raise HTTPException(403, 'Forbidden')
    db = get_db()
    if log_id == 'all':
        await db.activity_logs.delete_many({})
    else:
        await db.activity_logs.delete_one({'id': log_id})
    return {'success': True}


# ─── COMPANY SETTINGS ────────────────────────────────────────────────────────
@router.get("/company-settings")
async def get_company_settings(request: Request):
    await require_auth(request)
    db = get_db()
    settings = await db.company_settings.find_one({'type': 'general'}, {'_id': 0})
    if not settings:
        # Drift-safe: pakai doc lama (tanpa type) bila ada — JANGAN buat doc kedua.
        legacy = await db.company_settings.find_one({}, {'_id': 0})
        if legacy:
            patch = {'type': 'general', 'updated_at': now()}
            # migrasi nama field lama → kanonik
            if not legacy.get('company_phone') and legacy.get('phone'):
                patch['company_phone'] = legacy['phone']
            if not legacy.get('company_email') and legacy.get('email'):
                patch['company_email'] = legacy['email']
            for k in ('company_website', 'company_logo_url', 'pdf_header_line1',
                      'pdf_header_line2', 'pdf_footer_text'):
                patch.setdefault(k, legacy.get(k, ''))
            await db.company_settings.update_one({'id': legacy['id']}, {'$set': patch})
            settings = await db.company_settings.find_one({'id': legacy['id']}, {'_id': 0})
        else:
            settings = {
                'id': new_id(), 'type': 'general',
                'company_name': 'CV. Dewi Aditya', 'company_address': '',
                'company_phone': '', 'company_email': '', 'company_website': '',
                'company_logo_url': '', 'pdf_header_line1': '', 'pdf_header_line2': '',
                'pdf_footer_text': '', 'created_at': now(), 'updated_at': now()
            }
            await db.company_settings.insert_one(settings)
    return serialize_doc(settings)

@router.post("/company-settings")
async def save_company_settings(request: Request):
    user = await require_auth(request)
    if not check_role(user, ['admin']):
        raise HTTPException(403, 'Forbidden')
    db = get_db()
    body = await request.json()
    existing = await db.company_settings.find_one({'type': 'general'})
    data = {
        'company_name': body.get('company_name', ''), 'company_address': body.get('company_address', ''),
        'company_phone': body.get('company_phone', ''), 'company_email': body.get('company_email', ''),
        'company_website': body.get('company_website', ''), 'company_logo_url': body.get('company_logo_url', ''),
        'company_tagline': body.get('company_tagline', body.get('tagline', '')),
        'npwp': body.get('npwp', ''),
        'pdf_header_line1': body.get('pdf_header_line1', ''), 'pdf_header_line2': body.get('pdf_header_line2', ''),
        'pdf_footer_text': body.get('pdf_footer_text', ''),
        'updated_by': user['name'], 'updated_at': now()
    }
    if existing:
        await db.company_settings.update_one({'type': 'general'}, {'$set': data})
    else:
        await db.company_settings.insert_one({'id': new_id(), 'type': 'general', **data, 'created_at': now()})
    return serialize_doc(await db.company_settings.find_one({'type': 'general'}, {'_id': 0}))


# ─── RBAC ────────────────────────────────────────────────────────────────────
# SATU tempat konfigurasi akses (2026-08-06). Dokumen `roles` menyimpan:
#   name, description        -> identitas
#   portals[]                -> portal yang boleh dibuka (kosong = bawaan sistem)
#   hidden_modules[]         -> pintu menu yang disembunyikan
#   (koleksi `role_permissions`) -> izin aksi/approval
# Semua disimpan lewat SATU endpoint: POST /api/roles & PUT /api/roles/{id}.
# Katalog izin: `data/permission_catalog.py` (jangan buat katalog kedua).

async def _role_user_counts(db, roles: list) -> dict:
    """Hitung jumlah user per role (via `role_id` maupun `role` nama)."""
    counts: dict = {}
    by_id = await db.users.aggregate([
        {'$group': {'_id': '$role_id', 'n': {'$sum': 1}}}
    ]).to_list(1000)
    by_name = await db.users.aggregate([
        {'$group': {'_id': '$role', 'n': {'$sum': 1}}}
    ]).to_list(1000)
    id_map = {r['_id']: r['n'] for r in by_id if r.get('_id')}
    name_map = {str(r['_id']).lower(): r['n'] for r in by_name if r.get('_id')}
    for r in roles:
        counts[r['id']] = id_map.get(r['id'], 0) or name_map.get(str(r.get('name', '')).lower(), 0)
    return counts


@router.get("/roles")
async def get_roles(request: Request):
    user = await require_auth(request)
    if not check_role(user, ['admin']):
        raise HTTPException(403, 'Forbidden')
    db = get_db()
    roles = await db.roles.find({}, {'_id': 0}).sort('name', 1).to_list(500)
    perms_all = await db.role_permissions.find({}, {'_id': 0}).to_list(20000)
    by_role: dict = {}
    for p in perms_all:
        by_role.setdefault(p.get('role_id'), []).append(p)
    counts = await _role_user_counts(db, roles)
    result = []
    for r in roles:
        perms = by_role.get(r['id'], [])
        result.append({
            **serialize_doc(r),
            'portals': list(r.get('portals') or []),
            'hidden_modules': list(r.get('hidden_modules') or []),
            'permissions': serialize_doc(perms),
            'permission_keys': sorted({p.get('permission_key') for p in perms if p.get('permission_key')}),
            'user_count': counts.get(r['id'], 0),
        })
    return result

@router.post("/roles")
async def create_role(request: Request):
    user = await require_auth(request)
    if user.get('role') != 'superadmin':
        raise HTTPException(403, 'Forbidden')
    db = get_db()
    body = await request.json()
    name = (body.get('name') or '').strip()
    if not name:
        raise HTTPException(400, 'Nama role wajib diisi.')
    existing = await db.roles.find_one({'name': name})
    if existing:
        raise HTTPException(400, f"Role '{name}' sudah ada.")
    perms = validate_keys(body.get('permissions'))
    role = {'id': new_id(), 'name': name, 'description': body.get('description', ''),
            'portals': [str(p) for p in (body.get('portals') or [])],
            'hidden_modules': [str(m) for m in (body.get('hidden_modules') or [])],
            'is_system': False, 'created_at': now(), 'updated_at': now()}
    await db.roles.insert_one(role)
    if perms:
        await db.role_permissions.insert_many([
            {'id': new_id(), 'role_id': role['id'], 'permission_key': k, 'created_at': now()}
            for k in perms
        ])
    bump_rbac_cache()
    await log_audit(db, entity_type='role', entity_id=role['id'], action='create',
                    before=None, after={**role, 'permissions': sorted(perms)},
                    user=user, request=request)
    return JSONResponse(serialize_doc({**role, 'permission_keys': sorted(perms)}), status_code=201)

@router.put("/roles/{role_id}")
async def update_role(role_id: str, request: Request):
    """SATU-SATUNYA jalur simpan konfigurasi role (identitas + visibilitas + izin)."""
    user = await require_auth(request)
    if user.get('role') != 'superadmin':
        raise HTTPException(403, 'Forbidden')
    db = get_db()
    body = await request.json()
    before_role = await db.roles.find_one({'id': role_id}, {'_id': 0})
    if not before_role:
        raise HTTPException(404, 'Role tidak ditemukan.')
    before_perms = [p['permission_key'] for p in await db.role_permissions.find(
        {'role_id': role_id}, {'_id': 0, 'permission_key': 1}
    ).to_list(500)]

    _set = {'updated_at': now()}
    if 'name' in body:
        nm = (body.get('name') or '').strip()
        if not nm:
            raise HTTPException(400, 'Nama role wajib diisi.')
        clash = await db.roles.find_one({'name': nm, 'id': {'$ne': role_id}}, {'_id': 0, 'id': 1})
        if clash:
            raise HTTPException(400, f"Role '{nm}' sudah ada.")
        _set['name'] = nm
    if 'description' in body:
        _set['description'] = body.get('description', '')
    # Visibilitas: `portals` (portal yang boleh dibuka) & `hidden_modules`
    # (pintu menu yang disembunyikan). Keduanya opsional: bila kosong, bawaan
    # PORTAL_ACCESS di routes/shared.py dipakai.
    if 'portals' in body:
        _set['portals'] = [str(p) for p in (body.get('portals') or [])]
    if 'hidden_modules' in body:
        _set['hidden_modules'] = [str(m) for m in (body.get('hidden_modules') or [])]
    await db.roles.update_one({'id': role_id}, {'$set': _set})

    if 'permissions' in body:
        perms = validate_keys(body['permissions'])
        await db.role_permissions.delete_many({'role_id': role_id})
        if perms:
            await db.role_permissions.insert_many([
                {'id': new_id(), 'role_id': role_id, 'permission_key': k, 'created_at': now()}
                for k in perms
            ])

    after_role = await db.roles.find_one({'id': role_id}, {'_id': 0})
    after_perms = [p['permission_key'] for p in await db.role_permissions.find(
        {'role_id': role_id}, {'_id': 0, 'permission_key': 1}
    ).to_list(500)]
    bump_rbac_cache()
    await log_audit(db, entity_type='role', entity_id=role_id, action='update',
                    before={**before_role, 'permissions': sorted(before_perms)},
                    after={**after_role, 'permissions': sorted(after_perms)},
                    user=user, request=request)
    return serialize_doc({**after_role, 'permission_keys': sorted(after_perms)})

@router.delete("/roles/{role_id}")
async def delete_role(role_id: str, request: Request):
    user = await require_auth(request)
    if user.get('role') != 'superadmin':
        raise HTTPException(403, 'Forbidden')
    db = get_db()
    role = await db.roles.find_one({'id': role_id}, {'_id': 0})
    if not role:
        raise HTTPException(404, 'Role tidak ditemukan.')
    if role.get('is_system'):
        raise HTTPException(400, 'Role sistem tidak bisa dihapus.')
    used = await db.users.count_documents({'$or': [
        {'role_id': role_id}, {'role': role.get('name')}
    ]})
    if used:
        raise HTTPException(400, f"Role masih dipakai {used} pengguna. Pindahkan pengguna dulu.")
    before_perms = [p['permission_key'] for p in await db.role_permissions.find(
        {'role_id': role_id}, {'_id': 0, 'permission_key': 1}
    ).to_list(500)]
    await db.role_permissions.delete_many({'role_id': role_id})
    await db.roles.delete_one({'id': role_id})
    bump_rbac_cache()
    await log_audit(db, entity_type='role', entity_id=role_id, action='delete',
                    before={**role, 'permissions': sorted(before_perms)}, after=None,
                    user=user, request=request)
    return {'success': True}

# ─── Audit convenience: RBAC change history ─────────────────────────────────
@router.get("/roles/audit")
async def get_rbac_audit(request: Request):
    """Return RBAC audit trail (entity_type='role'), newest first."""
    user = await require_auth(request)
    if not check_role(user, ['admin']):
        raise HTTPException(403, 'Forbidden')
    db = get_db()
    sp = request.query_params
    q = {'entity_type': 'role'}
    if sp.get('role_id'):
        q['entity_id'] = sp['role_id']
    if sp.get('action'):
        q['action'] = sp['action']
    limit = q_int(sp.get('limit'), default=200, name='limit', minimum=1, maximum=1000, clamp=True)
    rows = await db.rahaza_audit_logs.find(q, {'_id': 0}).sort('timestamp', -1).limit(limit).to_list(500)
    return {'items': serialize_doc(rows), 'total': len(rows)}

@router.get("/permissions")
async def get_permissions(request: Request):
    """Katalog izin RBAC — SSOT tunggal di `data/permission_catalog.py`.

    * default            -> bentuk datar (kompatibel pemakai lama)
    * `?grouped=1`       -> bentuk bersarang portal > modul > izin (UI baru)
    """
    user = await require_auth(request)
    if not check_role(user, ['admin']):
        raise HTTPException(403, 'Forbidden')
    if str(request.query_params.get('grouped', '')).lower() in ('1', 'true', 'yes'):
        return {'groups': grouped_permissions(), 'total': len(all_permission_keys())}
    return flat_permissions()
