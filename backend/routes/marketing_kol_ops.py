"""marketing_kol — Admin: KOL Sessions + Item Requests + Catalog + FG Products + Leaderboard + Seed."""
from datetime import datetime, timezone, timedelta
from typing import Optional
from fastapi import Request, HTTPException
from fastapi.params import Query
from utils.query_guards import q_period
from database import get_db
from auth import hash_password, require_auth, serialize_doc, log_activity
from routes.marketing_kol_shared import (
    router, _uid, _now, _get_user, SessionCreate, CatalogItemCreate,
)
from core import stock_service


# ── LIVE SESSIONS ────────────────────────────────────────────────────────────────────

@router.post('/kol/sessions')
async def create_session(data: SessionCreate, request: Request):
    await require_auth(request)
    db = get_db()
    creator = await db.marketing_kol_creators.find_one({'id': data.creator_id}, {'_id': 0})
    if not creator:
        raise HTTPException(404, 'Creator tidak ditemukan')
    account = await db.marketing_platform_accounts.find_one({'id': data.account_id}, {'_id': 0})
    if not account:
        raise HTTPException(404, 'Account tidak ditemukan')
    session = {
        'id': _uid(), 'creator_id': data.creator_id, 'creator_name': creator['name'],
        'creator_code': creator['creator_code'], 'account_id': data.account_id,
        'account_name': account['account_name'], 'platform': data.platform,
        'date': data.date, 'session_name': data.session_name or f"Live {data.date}",
        'duration_minutes': data.duration_minutes, 'viewers': data.viewers,
        'peak_viewers': data.peak_viewers, 'revenue': data.revenue, 'orders': data.orders,
        'items_promoted': data.items_promoted or '', 'notes': data.notes or '',
        'created_at': _now(), 'created_by': _get_user(request).get('email', 'system'),
    }
    await db.marketing_creator_sessions.insert_one(session)
    # Sinkronkan ke Sales Marketing (revenue_type='live').
    try:
        from routes.marketing_live_sales_sync import sync_live_sales_to_marketing
        await sync_live_sales_to_marketing(db, data.account_id, data.date)
    except Exception:
        import logging
        logging.getLogger(__name__).warning("sync_live_sales gagal (admin session)", exc_info=True)
    user = _get_user(request)
    await log_activity(user.get('id', 'system'), user.get('name') or user.get('email', 'system'),
                       'create', 'marketing_creator_session',
                       f"Logged session for {creator['name']}: {data.date} - Rp{data.revenue:,.0f}")
    return serialize_doc({'message': 'Sesi berhasil dicatat', 'session': session})


@router.get('/kol/sessions')
async def list_sessions(
    request: Request,
    creator_id: Optional[str] = Query(None),
    account_id: Optional[str] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
):
    await require_auth(request)
    db = get_db()
    query = {}
    if creator_id:
        query['creator_id'] = creator_id
    if account_id:
        query['account_id'] = account_id
    if date_from or date_to:
        query['date'] = {}
        if date_from:
            query['date']['$gte'] = date_from
        if date_to:
            query['date']['$lte'] = date_to
    sessions = await db.marketing_creator_sessions.find(query, {'_id': 0}).sort('date', -1).to_list(500)
    return serialize_doc(sessions)


@router.delete('/kol/sessions/{session_id}')
async def delete_session(session_id: str, request: Request):
    await require_auth(request)
    db = get_db()
    sess = await db.marketing_creator_sessions.find_one({'id': session_id}, {'_id': 0})
    if not sess:
        raise HTTPException(404, 'Sesi tidak ditemukan')
    await db.marketing_creator_sessions.delete_one({'id': session_id})
    return serialize_doc({'message': 'Sesi dihapus'})


# ── ITEM REQUESTS ──────────────────────────────────────────────────────────────────

@router.get('/kol/requests')
async def list_requests(
    request: Request,
    status: Optional[str] = Query(None, description="pending | approved | rejected"),
    creator_id: Optional[str] = Query(None),
    account_id: Optional[str] = Query(None),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
):
    await require_auth(request)
    db = get_db()
    query = {}
    if status:
        query['status'] = status
    if creator_id:
        query['creator_id'] = creator_id
    if account_id:
        query['account_id'] = account_id
    total = await db.marketing_creator_item_requests.count_documents(query)
    skip = (page - 1) * limit
    requests = await db.marketing_creator_item_requests.find(
        query, {'_id': 0}
    ).sort('created_at', -1).skip(skip).limit(limit).to_list(500)
    fg_ids = list(set(r.get('fg_product_id') for r in requests if r.get('fg_product_id')))
    if fg_ids:
        # BUG-INV-12 fix: agregasi stok kanonik lintas semua baris/skema (bukan 1 lokasi saja).
        stock_map = await stock_service.onhand_map(fg_ids, db=db)
        for req in requests:
            req['current_stock'] = stock_map.get(req.get('fg_product_id'), 0)
    else:
        for req in requests:
            req['current_stock'] = 0
    return serialize_doc({
        'requests': requests,
        'pagination': {
            'total': total, 'page': page, 'limit': limit,
            'total_pages': (total + limit - 1) // limit if total > 0 else 1,
            'has_next': skip + limit < total, 'has_prev': page > 1,
        }
    })


@router.post('/kol/requests/{request_id}/approve')
async def approve_request(request_id: str, request: Request):
    from routes.shared import require_perm
    await require_perm(
        request, 'toko.approve', 'toko.manage',
        legacy_roles=('manager_marketing', 'pic_marketing', 'pic_toko', 'marketing_kol',
                      'manager', 'owner', 'admin', 'superadmin'),
        message='Akses ditolak: Anda tidak berhak menyetujui permintaan kreator.')
    db = get_db()
    req = await db.marketing_creator_item_requests.find_one({'id': request_id}, {'_id': 0})
    if not req:
        raise HTTPException(404, 'Request tidak ditemukan')
    if req['status'] != 'pending':
        raise HTTPException(400, f"Request sudah {req['status']}")
    user = _get_user(request)
    await db.marketing_creator_item_requests.update_one(
        {'id': request_id}, {'$set': {'status': 'approved', 'reviewed_at': _now(), 'reviewed_by': user.get('email', 'admin')}}
    )
    await log_activity(user.get('id', 'system'), user.get('name') or user.get('email', 'system'),
                       'approve', 'marketing_creator_request',
                       f"Approved request {request_id} from {req['creator_name']} for {req['product_name']}")
    return serialize_doc({'message': 'Request disetujui'})


@router.post('/kol/requests/{request_id}/reject')
async def reject_request(request_id: str, reason: str, request: Request):
    from routes.shared import require_perm
    await require_perm(
        request, 'toko.approve', 'toko.manage',
        legacy_roles=('manager_marketing', 'pic_marketing', 'pic_toko', 'marketing_kol',
                      'manager', 'owner', 'admin', 'superadmin'),
        message='Akses ditolak: Anda tidak berhak menolak permintaan kreator.')
    db = get_db()
    req = await db.marketing_creator_item_requests.find_one({'id': request_id}, {'_id': 0})
    if not req:
        raise HTTPException(404, 'Request tidak ditemukan')
    if req['status'] != 'pending':
        raise HTTPException(400, f"Request sudah {req['status']}")
    user = _get_user(request)
    await db.marketing_creator_item_requests.update_one(
        {'id': request_id},
        {'$set': {'status': 'rejected', 'reviewed_at': _now(), 'reviewed_by': user.get('email', 'admin'), 'rejection_reason': reason}}
    )
    await log_activity(user.get('id', 'system'), user.get('name') or user.get('email', 'system'),
                       'reject', 'marketing_creator_request', f"Rejected request {request_id}: {reason}")
    return serialize_doc({'message': 'Request ditolak', 'reason': reason})


# ── CATALOG MANAGEMENT ───────────────────────────────────────────────────────────

@router.get('/kol/catalog')
async def list_catalog(request: Request, account_id: Optional[str] = Query(None), is_active: Optional[bool] = Query(None)):
    await require_auth(request)
    db = get_db()
    query = {}
    if account_id:
        query['account_id'] = account_id
    if is_active is not None:
        query['is_active'] = is_active
    items = await db.marketing_creator_catalog.find(query, {'_id': 0}).sort('product_name', 1).to_list(500)
    # BUG-INV-12 fix: agregasi stok kanonik lintas semua baris/skema.
    fg_ids = [it.get('fg_product_id') for it in items if it.get('fg_product_id')]
    stock_map = await stock_service.onhand_map(fg_ids, db=db) if fg_ids else {}
    for item in items:
        fg_id = item.get('fg_product_id')
        item['stock_qty'] = stock_map.get(fg_id, 0) if fg_id else 0
    return serialize_doc(items)


@router.post('/kol/catalog')
async def add_catalog_item(data: CatalogItemCreate, request: Request):
    await require_auth(request)
    db = get_db()
    account = await db.marketing_platform_accounts.find_one({'id': data.account_id}, {'_id': 0})
    if not account:
        raise HTTPException(404, 'Account tidak ditemukan')
    if await db.marketing_creator_catalog.find_one({'account_id': data.account_id, 'sku': data.sku}):
        raise HTTPException(400, f"SKU '{data.sku}' sudah ada di katalog akun ini")
    item = {
        'id': _uid(), 'account_id': data.account_id, 'account_name': account['account_name'],
        'fg_product_id': data.fg_product_id, 'product_name': data.product_name,
        'sku': data.sku, 'category': data.category or '', 'unit_price': data.unit_price,
        'description': data.description or '', 'is_active': data.is_active,
        'created_at': _now(), 'created_by': _get_user(request).get('email', 'system'),
    }
    await db.marketing_creator_catalog.insert_one(item)
    user = _get_user(request)
    await log_activity(user.get('id', 'system'), user.get('name') or user.get('email', 'system'),
                       'create', 'marketing_creator_catalog', f"Added catalog item: {data.product_name} ({data.sku})")
    return serialize_doc({'message': 'Produk berhasil ditambahkan ke katalog', 'item': item})


@router.put('/kol/catalog/{item_id}')
async def update_catalog_item(item_id: str, data: CatalogItemCreate, request: Request):
    await require_auth(request)
    db = get_db()
    item = await db.marketing_creator_catalog.find_one({'id': item_id}, {'_id': 0})
    if not item:
        raise HTTPException(404, 'Item katalog tidak ditemukan')
    update_data = {
        'product_name': data.product_name, 'sku': data.sku, 'category': data.category or '',
        'unit_price': data.unit_price, 'description': data.description or '',
        'is_active': data.is_active, 'fg_product_id': data.fg_product_id, 'updated_at': _now(),
    }
    await db.marketing_creator_catalog.update_one({'id': item_id}, {'$set': update_data})
    updated = await db.marketing_creator_catalog.find_one({'id': item_id}, {'_id': 0})
    return serialize_doc({'message': 'Item katalog diupdate', 'item': updated})


@router.delete('/kol/catalog/{item_id}')
async def remove_catalog_item(item_id: str, request: Request):
    await require_auth(request)
    db = get_db()
    item = await db.marketing_creator_catalog.find_one({'id': item_id}, {'_id': 0})
    if not item:
        raise HTTPException(404, 'Item katalog tidak ditemukan')
    await db.marketing_creator_catalog.update_one({'id': item_id}, {'$set': {'is_active': False, 'updated_at': _now()}})
    return serialize_doc({'message': 'Item katalog dinonaktifkan'})


@router.get('/kol/fg-products')
async def list_fg_products(request: Request, search: Optional[str] = Query(None)):
    await require_auth(request)
    db = get_db()
    query = {'type': 'fg'}
    if search:
        query['$or'] = [{'name': {'$regex': search, '$options': 'i'}}, {'code': {'$regex': search, '$options': 'i'}}]
    materials = await db.rahaza_materials.find(query, {'_id': 0}).sort('name', 1).limit(100).to_list(500)
    # BUG-INV-12 fix: agregasi stok kanonik lintas semua baris/skema.
    stock_map = await stock_service.onhand_map([m['id'] for m in materials], db=db)
    for mat in materials:
        mat['stock_qty'] = stock_map.get(mat['id'], 0)
    return serialize_doc(materials)


# ── LEADERBOARD ────────────────────────────────────────────────────────────────────

@router.get('/kol/leaderboard')
async def get_leaderboard(request: Request, month: Optional[str] = Query(None, description="YYYY-MM")):
    await require_auth(request)
    db = get_db()
    if not month:
        month = _now().strftime('%Y-%m')
    # BUG-R11-A (FASE 11): `int(month.split('-')[1])` dulu dieksekusi mentah,
    # jadi `?month=99` melempar ValueError/IndexError → HTTP 500.
    # Sekarang periode divalidasi lebih dulu dan input salah dibalas HTTP 400.
    year, mon = q_period(month, name='month')
    month = f'{year:04d}-{mon:02d}'
    date_from = f'{month}-01'
    next_month = datetime(year, mon, 1, tzinfo=timezone.utc) + timedelta(days=32)
    date_to = (next_month.replace(day=1) - timedelta(days=1)).strftime('%Y-%m-%d')
    creators = await db.marketing_kol_creators.find({'status': 'active'}, {'_id': 0, 'login_password_hash': 0}).to_list(500)
    leaderboard = []
    for creator in creators:
        sessions = await db.marketing_creator_sessions.find(
            {'creator_id': creator['id'], 'date': {'$gte': date_from, '$lte': date_to}}, {'_id': 0}
        ).to_list(500)
        total_revenue = round(sum(s.get('revenue', 0) for s in sessions))
        total_viewers = sum(s.get('viewers', 0) for s in sessions)
        total_orders  = sum(s.get('orders', 0) for s in sessions)
        total_sessions = len(sessions)
        kpi = creator.get('kpi_targets', {})
        leaderboard.append({
            'creator_id': creator.get('id'), 'creator_code': creator.get('creator_code', ''),
            'name': creator.get('name') or creator.get('real_name', 'Unknown'),
            'platforms': creator.get('platforms', {}),
            'total_revenue': total_revenue, 'total_viewers': total_viewers,
            'total_orders': total_orders, 'total_sessions': total_sessions,
            'kpi_revenue_target': kpi.get('monthly_revenue', 0),
            'kpi_revenue_pct': round(total_revenue / kpi['monthly_revenue'] * 100, 1) if kpi.get('monthly_revenue') else None,
        })
    leaderboard.sort(key=lambda x: x['total_revenue'], reverse=True)
    for i, entry in enumerate(leaderboard):
        entry['rank'] = i + 1
    return serialize_doc({'month': month, 'leaderboard': leaderboard})


# ── SEED DEMO ───────────────────────────────────────────────────────────────────────

async def _seed_kol_catalog(db, account_id: str) -> int:
    demo_products = [
        {'sku': 'KOL-PROD-001', 'product_name': 'Kemeja Batik Premium',  'category': 'Atasan',    'price': 189000, 'description': 'Kemeja batik motif kawung premium cotton'},
        {'sku': 'KOL-PROD-002', 'product_name': 'Celana Chino Slim Fit', 'category': 'Bawahan',   'price': 249000, 'description': 'Celana chino slim fit berbagai warna'},
        {'sku': 'KOL-PROD-003', 'product_name': 'Gaun Dress Floral',     'category': 'Dress',     'price': 329000, 'description': 'Gaun motif bunga untuk casual & formal'},
        {'sku': 'KOL-PROD-004', 'product_name': 'Blouse Polos Linen',    'category': 'Atasan',    'price': 159000, 'description': 'Blouse bahan linen adem untuk sehari-hari'},
        {'sku': 'KOL-PROD-005', 'product_name': 'Rok Midi Plisket',      'category': 'Bawahan',   'price': 199000, 'description': 'Rok midi plisket elegan'},
        {'sku': 'KOL-PROD-006', 'product_name': 'Jaket Denim Classic',   'category': 'Outerwear', 'price': 379000, 'description': 'Jaket denim klasik unisex'},
    ]
    created = 0
    for p in demo_products:
        existing = await db.marketing_creator_catalog.find_one({'sku': p['sku'], 'account_id': account_id})
        if not existing:
            await db.marketing_creator_catalog.insert_one({
                'id': _uid(), 'account_id': account_id, 'sku': p['sku'],
                'product_name': p['product_name'], 'category': p.get('category', ''),
                'description': p.get('description', ''), 'price': p['price'],
                'fg_product_id': None, 'images': [], 'is_active': True, 'stock_note': 'Ready stock',
                'created_at': _now(), 'created_by': 'seed',
            })
            created += 1
    return created


@router.post('/kol/seed-demo')
async def seed_kol_demo(request: Request):
    await require_auth(request)
    db = get_db()
    account = await db.marketing_platform_accounts.find_one({'status': 'active'}, {'_id': 0})
    if not account:
        raise HTTPException(400, 'Tidak ada akun aktif. Seed akun terlebih dahulu.')
    demo_creators = [
        {'id': _uid(), 'creator_code': 'KOL-001', 'name': 'Ayu Dewi',
         'login_email': 'ayu.creator@demo.com', 'login_password_hash': hash_password('Creator@123'),
         'phone': '08111222333', 'platforms': {'tiktok': '@ayu_fashion', 'shopee': 'ayu_dewi_store'},
         'assigned_account_ids': [account['id']], 'kpi_targets': {'monthly_revenue': 50000000, 'monthly_sessions': 12, 'monthly_viewers': 80000},
         'notes': 'Top creator fashion', 'status': 'active', 'last_login_at': None, 'created_at': _now(), 'created_by': 'seed', 'updated_at': _now()},
        {'id': _uid(), 'creator_code': 'KOL-002', 'name': 'Budi Santoso',
         'login_email': 'budi.creator@demo.com', 'login_password_hash': hash_password('Creator@123'),
         'phone': '08222333444', 'platforms': {'tiktok': '@budi_daily', 'instagram': 'budi.santoso'},
         'assigned_account_ids': [account['id']], 'kpi_targets': {'monthly_revenue': 30000000, 'monthly_sessions': 8, 'monthly_viewers': 50000},
         'notes': 'Lifestyle creator', 'status': 'active', 'last_login_at': None, 'created_at': _now(), 'created_by': 'seed', 'updated_at': _now()},
        {'id': _uid(), 'creator_code': 'KOL-003', 'name': 'Citra Lestari',
         'login_email': 'citra.creator@demo.com', 'login_password_hash': hash_password('Creator@123'),
         'phone': '08333444555', 'platforms': {'shopee': 'citra_official', 'tiktok': '@citra_style'},
         'assigned_account_ids': [account['id']], 'kpi_targets': {'monthly_revenue': 40000000, 'monthly_sessions': 10, 'monthly_viewers': 60000},
         'notes': 'Beauty & fashion', 'status': 'active', 'last_login_at': None, 'created_at': _now(), 'created_by': 'seed', 'updated_at': _now()},
    ]
    created = 0
    for c in demo_creators:
        if not await db.marketing_kol_creators.find_one({'creator_code': c['creator_code']}):
            await db.marketing_kol_creators.insert_one(c)
            created += 1
    month = _now().strftime('%Y-%m')
    created_sessions = 0
    for idx, c in enumerate(demo_creators):
        creator_doc = await db.marketing_kol_creators.find_one({'creator_code': c['creator_code']}, {'_id': 0})
        if not creator_doc:
            continue
        for day in [5, 12, 19]:
            date_str = f"{month}-{day:02d}"
            if not await db.marketing_creator_sessions.find_one({'creator_id': creator_doc['id'], 'date': date_str}):
                await db.marketing_creator_sessions.insert_one({
                    'id': _uid(), 'creator_id': creator_doc['id'], 'creator_name': creator_doc['name'],
                    'creator_code': creator_doc['creator_code'], 'account_id': account['id'],
                    'account_name': account['account_name'], 'platform': account['platform'],
                    'date': date_str, 'session_name': f"Live Sesi {day}",
                    'duration_minutes': 90 + idx * 30, 'viewers': 1500 + idx * 500 + day * 100,
                    'peak_viewers': 2000 + idx * 600 + day * 150, 'revenue': (5000000 + idx * 2000000 + day * 100000),
                    'orders': 50 + idx * 20 + day, 'items_promoted': ['Kemeja Batik', 'Celana Chino'],
                    'notes': 'Sesi demo', 'created_at': _now(), 'created_by': 'seed',
                })
                created_sessions += 1
    return serialize_doc({
        'message': 'Demo KOL data seeded',
        'creators_created': created,
        'sessions_created': created_sessions,
        'catalog_created': await _seed_kol_catalog(db, account['id']),
        'note': 'Default password telah di-set untuk akun demo. Hubungi admin untuk credential.',
    })
