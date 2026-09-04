"""marketing_kol — Admin: KOL Creator CRUD."""
from datetime import datetime, timezone, timedelta
from typing import Optional
from fastapi import Request, HTTPException
from pydantic import BaseModel, Field
from fastapi.params import Query
from database import get_db
from auth import hash_password, require_auth, serialize_doc, log_activity
from routes.marketing_kol_shared import router, _uid, _now, _get_user, CreatorCreate, CreatorUpdate
from collections import defaultdict as _dd


@router.post('/kol/creators')
async def create_creator(data: CreatorCreate, request: Request):
    await require_auth(request)
    db = get_db()
    email = (data.login_email or '').lower().strip()
    if data.creator_type not in ('new', 'kontrak', 'continue'):
        raise HTTPException(400, "creator_type harus new | kontrak | continue")
    if email and await db.marketing_kol_creators.find_one({'login_email': email}):
        raise HTTPException(400, f"Email '{data.login_email}' sudah terdaftar")
    if email and not data.login_password:
        raise HTTPException(400, "Email diisi tetapi password kosong — akun portal tidak "
                                 "akan bisa dipakai login. Isi password minimal 6 karakter.")
    if await db.marketing_kol_creators.find_one({'creator_code': data.creator_code}):
        raise HTTPException(400, f"Kode creator '{data.creator_code}' sudah ada")
    creator = {
        'id': _uid(), 'creator_code': data.creator_code, 'name': data.name,
        'login_email': email,
        'login_password_hash': hash_password(data.login_password) if data.login_password else '',
        'portal_account_ready': bool(email and data.login_password),
        'creator_type': data.creator_type,
        'domicile': (data.domicile or '').strip(),
        'domicile_detail': (data.domicile_detail or '').strip(),
        'phone': data.phone or '', 'platforms': data.platforms or {},
        'assigned_account_ids': data.assigned_account_ids or [],
        'kpi_targets': data.kpi_targets or {'monthly_revenue': 0, 'monthly_sessions': 0, 'monthly_viewers': 0},
        'notes': data.notes or '', 'status': 'active', 'last_login_at': None,
        'created_at': _now(), 'created_by': _get_user(request).get('email', 'system'), 'updated_at': _now(),
    }
    await db.marketing_kol_creators.insert_one(creator)
    creator.pop('login_password_hash', None)
    user = _get_user(request)
    await log_activity(user.get('id', 'system'), user.get('name') or user.get('email', 'system'),
                       'create', 'marketing_kol_creator', f"Created creator: {data.name} ({data.creator_code})")
    return serialize_doc({'message': 'Creator berhasil dibuat', 'creator': creator})


@router.get('/kol/creators')
async def list_creators(
    request: Request,
    status: Optional[str] = Query(None),
    account_id: Optional[str] = Query(None, description="Filter by assigned account"),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
):
    await require_auth(request)
    db = get_db()
    # F14 — lihat alasan yang sama pada master host live.
    from core.marketing_master_seed import ensure_demo_creators
    await ensure_demo_creators(db)
    query = {}
    if status:
        query['status'] = status
    if account_id:
        query['assigned_account_ids'] = account_id
    total = await db.marketing_kol_creators.count_documents(query)
    skip = (page - 1) * limit
    creators = await db.marketing_kol_creators.find(
        query, {'_id': 0, 'login_password_hash': 0}
    ).sort('created_at', -1).skip(skip).limit(limit).to_list(500)
    month = _now().strftime('%Y-%m')
    date_from = f'{month}-01'
    year, mon = int(month.split('-')[0]), int(month.split('-')[1])
    next_month = datetime(year, mon, 1, tzinfo=timezone.utc) + timedelta(days=32)
    date_to = (next_month.replace(day=1) - timedelta(days=1)).strftime('%Y-%m-%d')
    creator_ids = [c['id'] for c in creators]
    all_sessions = await db.marketing_creator_sessions.find(
        {'creator_id': {'$in': creator_ids}, 'date': {'$gte': date_from, '$lte': date_to}},
        {'_id': 0, 'creator_id': 1, 'revenue': 1, 'viewers': 1}
    ).to_list(500)
    sessions_by_creator = _dd(list)
    for s in all_sessions:
        sessions_by_creator[s['creator_id']].append(s)
    for c in creators:
        sessions = sessions_by_creator.get(c['id'], [])
        c['this_month'] = {
            'sessions': len(sessions),
            'revenue': round(sum(s.get('revenue', 0) for s in sessions)),
            'viewers': sum(s.get('viewers', 0) for s in sessions),
        }
    return serialize_doc({
        'creators': creators,
        'pagination': {
            'total': total, 'page': page, 'limit': limit,
            'total_pages': (total + limit - 1) // limit if total > 0 else 1,
            'has_next': skip + limit < total, 'has_prev': page > 1,
        }
    })


@router.get('/kol/creators/{creator_id}')
async def get_creator(creator_id: str, request: Request):
    await require_auth(request)
    db = get_db()
    creator = await db.marketing_kol_creators.find_one({'id': creator_id}, {'_id': 0, 'login_password_hash': 0})
    if not creator:
        raise HTTPException(404, 'Creator tidak ditemukan')
    assigned = await db.marketing_platform_accounts.find(
        {'id': {'$in': creator.get('assigned_account_ids', [])}}, {'_id': 0}
    ).to_list(500)
    creator['assigned_accounts'] = assigned
    return serialize_doc(creator)


@router.put('/kol/creators/{creator_id}')
async def update_creator(creator_id: str, data: CreatorUpdate, request: Request):
    await require_auth(request)
    db = get_db()
    creator = await db.marketing_kol_creators.find_one({'id': creator_id}, {'_id': 0})
    if not creator:
        raise HTTPException(404, 'Creator tidak ditemukan')
    update_data = {}
    if data.name is not None:
        update_data['name'] = data.name
    if data.creator_type is not None:
        if data.creator_type not in ('new', 'kontrak', 'continue'):
            raise HTTPException(400, "creator_type harus new | kontrak | continue")
        update_data['creator_type'] = data.creator_type
    if data.domicile is not None:
        update_data['domicile'] = data.domicile.strip()
    if data.domicile_detail is not None:
        update_data['domicile_detail'] = data.domicile_detail.strip()
    if data.login_email is not None:
        em = data.login_email.lower().strip()
        if em:
            dup = await db.marketing_kol_creators.find_one(
                {'login_email': em, 'id': {'$ne': creator_id}}, {'_id': 0, 'id': 1})
            if dup:
                raise HTTPException(400, f"Email '{em}' sudah dipakai kreator lain")
        update_data['login_email'] = em
    if data.phone is not None:
        update_data['phone'] = data.phone
    if data.platforms is not None:
        update_data['platforms'] = data.platforms
    if data.assigned_account_ids is not None:
        update_data['assigned_account_ids'] = data.assigned_account_ids
    if data.kpi_targets is not None:
        update_data['kpi_targets'] = data.kpi_targets
    if data.notes is not None:
        update_data['notes'] = data.notes
    if data.status is not None:
        if data.status not in ('active', 'inactive'):
            raise HTTPException(400, 'status harus active atau inactive')
        update_data['status'] = data.status
    if data.login_password:
        update_data['login_password_hash'] = hash_password(data.login_password)
        update_data['portal_account_ready'] = bool(
            update_data.get('login_email') or creator.get('login_email'))
    update_data['updated_at'] = _now()
    await db.marketing_kol_creators.update_one({'id': creator_id}, {'$set': update_data})
    user = _get_user(request)
    await log_activity(user.get('id', 'system'), user.get('name') or user.get('email', 'system'),
                       'update', 'marketing_kol_creator', f"Updated creator: {creator['name']}")
    updated = await db.marketing_kol_creators.find_one({'id': creator_id}, {'_id': 0, 'login_password_hash': 0})
    return serialize_doc({'message': 'Creator berhasil diupdate', 'creator': updated})


@router.delete('/kol/creators/{creator_id}')
async def deactivate_creator(creator_id: str, request: Request):
    await require_auth(request)
    db = get_db()
    creator = await db.marketing_kol_creators.find_one({'id': creator_id}, {'_id': 0})
    if not creator:
        raise HTTPException(404, 'Creator tidak ditemukan')
    await db.marketing_kol_creators.update_one({'id': creator_id}, {'$set': {'status': 'inactive', 'updated_at': _now()}})
    user = _get_user(request)
    await log_activity(user.get('id', 'system'), user.get('name') or user.get('email', 'system'),
                       'deactivate', 'marketing_kol_creator', f"Deactivated creator: {creator['name']}")
    return serialize_doc({'message': 'Creator dinonaktifkan'})


class PortalAccountIn(BaseModel):
    login_email: str = Field(..., min_length=5)
    login_password: str = Field(..., min_length=6)


@router.post('/kol/creators/{creator_id}/portal-account')
async def set_portal_account(creator_id: str, data: PortalAccountIn, request: Request):
    """SESI #34 — **buat / setel ulang akun portal kreator**.

    Kenapa endpoint ini ada: 3 kreator demo di database lahir dari penyemai lama
    TANPA `login_email`/`login_password_hash` sama sekali. Akibatnya pemilik
    membuka Portal Kreator dan tidak bisa login — dan tidak ada satu pun layar
    yang bisa memperbaikinya (PUT hanya bisa mengganti password, bukan membuat
    email). Sekarang staf marketing bisa membuatkan akunnya, dan layar bisa
    mengatakan kreator mana yang BELUM punya akun (`portal_account_ready`).
    """
    await require_auth(request)
    db = get_db()
    creator = await db.marketing_kol_creators.find_one({'id': creator_id}, {'_id': 0})
    if not creator:
        raise HTTPException(404, 'Creator tidak ditemukan')
    email = data.login_email.lower().strip()
    dup = await db.marketing_kol_creators.find_one(
        {'login_email': email, 'id': {'$ne': creator_id}}, {'_id': 0, 'id': 1})
    if dup:
        raise HTTPException(400, f"Email '{email}' sudah dipakai kreator lain")
    await db.marketing_kol_creators.update_one({'id': creator_id}, {'$set': {
        'login_email': email,
        'login_password_hash': hash_password(data.login_password),
        'portal_account_ready': True,
        'status': creator.get('status') or 'active',
        'updated_at': _now(),
    }})
    user = _get_user(request)
    await log_activity(user.get('id', 'system'), user.get('name') or user.get('email', 'system'),
                       'update', 'marketing_kol_creator',
                       f"Akun portal kreator {creator.get('name')} disetel ({email})")
    return {'ok': True, 'message': f"Akun portal siap dipakai: {email}",
            'creator_id': creator_id, 'login_email': email}
