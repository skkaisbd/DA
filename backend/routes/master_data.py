"""
Master Data: Garments, Buyers, Products, Product Variants
Extracted from server.py monolith.

[FASE 4 CLEANUP — DEPRECATION NOTICE]
The `/api/products*` and `/api/product-variants*` endpoints below (collections
`products` / `product_variants`) are DEPRECATED. They are no longer wired to any
active UI picker:
  · PO Internal → uses `rahaza_models` + `rahaza_model_variants`
  · PO Maklon   → uses buyer-catalog (`dewi_maklon_buyer_catalog`)
  · `ProductsModule.jsx` (the only CRUD screen) has been de-registered from the nav.
They are intentionally KEPT (not removed) for backward-compat / historical data
access and for the one-off migration script `migrations/migrate_products_to_rahaza.py`.
Do NOT build new features on these endpoints — use rahaza_models / buyer-catalog.
"""
from fastapi import APIRouter, Request, HTTPException, UploadFile, File
from fastapi.responses import JSONResponse
from database import get_db
from auth import (require_auth, check_role, hash_password, log_activity, serialize_doc, generate_password)
from routes.shared import new_id, now
from utils.cascade_delete import cascade_delete_po  # P1 refactor: moved to utils/ (was backend root)
import logging
import re
from utils.query_guards import q_int

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["master_data"])

# ─── GARMENTS ────────────────────────────────────────────────────────────────
@router.get("/garments")
async def get_garments(request: Request):
    """Daftar vendor/CMT untuk picker (Kirim Material, Work Order, Overproduction).

    SSOT = `vendor_partners` (dikelola di menu "Vendor CMT" & dipakai flow maklon).
    Data legacy `garments` (bila ada) tetap di-union agar tidak ada yang hilang.
    Dinormalisasi ke bentuk garment (garment_name / garment_code / status) supaya
    kompatibel dengan konsumen yang sudah ada.
    """
    user = await require_auth(request)
    db = get_db()
    sp = request.query_params
    search = sp.get('search')
    status = sp.get('status')

    # Legacy collection (umumnya kosong pada instalasi baru)
    legacy = await db.garments.find({}, {'_id': 0}).sort('created_at', -1).to_list(500)

    # Kanonik: vendor_partners (sumber CMT terkini — sama dengan maklon)
    partners = await db.vendor_partners.find({}, {'_id': 0}).sort('name', 1).to_list(500)
    normalized = []
    for p in partners:
        # Kenali beberapa varian field status: `active` (seed), `is_active` (dibuat via UI),
        # atau `status` string. Default AKTIF bila tidak ada penanda apa pun.
        if 'active' in p:
            is_active = bool(p.get('active', True))
        elif 'is_active' in p:
            is_active = bool(p.get('is_active', True))
        elif 'status' in p:
            is_active = (p.get('status') == 'active')
        else:
            is_active = True
        normalized.append({
            **p,
            'garment_name': p.get('garment_name') or p.get('name') or '',
            'garment_code': p.get('garment_code') or p.get('code') or '',
            'status': 'active' if is_active else 'inactive',
        })

    # Union: legacy dulu, lalu partner yang belum ada (dedup by id)
    seen_ids = {d.get('id') for d in legacy}
    docs = legacy + [d for d in normalized if d.get('id') not in seen_ids]

    # Filter role vendor (hanya lihat dirinya)
    if user.get('role') == 'vendor':
        docs = [d for d in docs if d.get('id') == user.get('vendor_id')]
    # Filter status
    if status:
        docs = [d for d in docs if d.get('status') == status]
    # Filter pencarian (nama / kode)
    if search:
        s = search.lower()
        docs = [d for d in docs
                if s in (d.get('garment_name') or '').lower()
                or s in (d.get('garment_code') or '').lower()]

    return serialize_doc(docs)

@router.get("/garments/{gid}")
async def get_garment(gid: str, request: Request):
    await require_auth(request)
    db = get_db()
    doc = await db.garments.find_one({'id': gid}, {'_id': 0})
    if not doc:
        raise HTTPException(404, 'Not found')
    return serialize_doc(doc)

@router.post("/garments")
async def create_garment(request: Request):
    user = await require_auth(request)
    if not check_role(user, ['admin']):
        raise HTTPException(403, 'Forbidden')
    db = get_db()
    body = await request.json()
    garment_id = new_id()
    code_slug = (body.get('garment_code', garment_id)).lower()
    code_slug = ''.join(c for c in code_slug if c.isalnum())
    vendor_email = f"vendor.{code_slug}@garment.com"
    raw_password = generate_password(10)
    hashed = hash_password(raw_password)
    await db.users.insert_one({
        'id': new_id(), 'name': body.get('garment_name', ''), 'email': vendor_email,
        'password': hashed, 'role': 'vendor', 'vendor_id': garment_id,
        'status': 'active', 'created_at': now(), 'updated_at': now()
    })
    garment = {'id': garment_id, **body, 'status': body.get('status', 'active'),
               'login_email': vendor_email,
               'created_at': now(), 'updated_at': now()}
    await db.garments.insert_one(garment)
    await log_activity(user['id'], user['name'], 'Create', 'Garments', f"Created garment: {garment.get('garment_name')}")
    result = serialize_doc(garment)
    # One-time password reveal (NOT persisted in DB)
    result['vendor_account'] = {'email': vendor_email, 'password': raw_password}
    return JSONResponse(result, status_code=201)

@router.put("/garments/{gid}")
async def update_garment(gid: str, request: Request):
    user = await require_auth(request)
    if not check_role(user, ['admin']):
        raise HTTPException(403, 'Forbidden')
    db = get_db()
    body = await request.json()
    body.pop('_id', None)
    body.pop('id', None)
    body.pop('vendor_account', None)
    await db.garments.update_one({'id': gid}, {'$set': {**body, 'updated_at': now()}})
    if body.get('garment_name'):
        await db.users.update_one({'vendor_id': gid}, {'$set': {'name': body['garment_name'], 'updated_at': now()}})
    await log_activity(user['id'], user['name'], 'Update', 'Garments', f"Updated garment: {gid}")
    doc = await db.garments.find_one({'id': gid}, {'_id': 0})
    return serialize_doc(doc)

@router.delete("/garments/{gid}")
async def delete_garment(gid: str, request: Request):
    user = await require_auth(request)
    if user.get('role') != 'superadmin':
        raise HTTPException(403, 'Forbidden: Only Superadmin can delete')
    db = get_db()
    doc = await db.garments.find_one({'id': gid})
    if not doc:
        raise HTTPException(404, 'Not found')
    vendor_pos = await db.production_pos.find({'vendor_id': gid}).to_list(500)
    for po in vendor_pos:
        await cascade_delete_po(po['id'])
    await db.material_requests.delete_many({'vendor_id': gid})
    await db.material_defect_reports.delete_many({'vendor_id': gid})
    await db.users.delete_many({'vendor_id': gid})
    await db.garments.delete_one({'id': gid})
    await log_activity(user['id'], user['name'], 'Delete', 'Garments', f"Cascade deleted garment: {doc.get('garment_name')}")
    return {'success': True, 'deleted_pos': len(vendor_pos)}

# ─── BUYERS (Master Data) ────────────────────────────────────────────────────
@router.get("/buyers")
async def get_buyers(request: Request):
    await require_auth(request)
    db = get_db()
    sp = request.query_params
    query = {}
    search = sp.get('search')
    if search:
        query['$or'] = [{'buyer_name': {'$regex': re.escape(search), '$options': 'i'}}, {'buyer_code': {'$regex': re.escape(search), '$options': 'i'}}]
    if sp.get('status'):
        query['status'] = sp['status']
    page = q_int(sp.get('page'), default=1, name='page', minimum=1)
    limit = q_int(sp.get('limit'), default=100, name='limit', minimum=1, maximum=500)
    skip = (page - 1) * limit
    total = await db.buyers.count_documents(query)
    docs = await db.buyers.find(query, {'_id': 0}).sort('created_at', -1).skip(skip).limit(limit).to_list(500)
    return {'data': serialize_doc(docs), 'total': total, 'page': page, 'limit': limit} if sp.get('paginated') else serialize_doc(docs)

@router.get("/buyers/{bid}")
async def get_buyer(bid: str, request: Request):
    await require_auth(request)
    db = get_db()
    doc = await db.buyers.find_one({'id': bid}, {'_id': 0})
    if not doc:
        raise HTTPException(404, 'Not found')
    return serialize_doc(doc)

@router.post("/buyers")
async def create_buyer(request: Request):
    user = await require_auth(request)
    if not check_role(user, ['admin']):
        raise HTTPException(403, 'Forbidden')
    db = get_db()
    body = await request.json()
    buyer_id = new_id()
    code_slug = (body.get('buyer_code', buyer_id)).lower()
    code_slug = ''.join(c for c in code_slug if c.isalnum())
    buyer_email = f"buyer.{code_slug}@garment.com"
    raw_password = generate_password(10)
    hashed = hash_password(raw_password)
    # Auto-create buyer portal account
    await db.users.insert_one({
        'id': new_id(), 'name': body.get('buyer_name', ''), 'email': buyer_email,
        'password': hashed, 'role': 'buyer', 'buyer_id': buyer_id,
        'customer_name': body.get('buyer_name', ''),
        'buyer_company': body.get('buyer_name', ''),
        'status': 'active', 'created_at': now(), 'updated_at': now()
    })
    buyer = {
        'id': buyer_id, **body, 'status': body.get('status', 'active'),
        'login_email': buyer_email,
        'created_at': now(), 'updated_at': now()
    }
    await db.buyers.insert_one(buyer)
    await log_activity(user['id'], user['name'], 'Create', 'Buyers', f"Created buyer: {body.get('buyer_name')}, account: {buyer_email}")
    result = serialize_doc(buyer)
    # One-time password reveal (NOT persisted in DB)
    result['buyer_account'] = {'email': buyer_email, 'password': raw_password}
    return JSONResponse(result, status_code=201)

@router.put("/buyers/{bid}")
async def update_buyer(bid: str, request: Request):
    user = await require_auth(request)
    if not check_role(user, ['admin']):
        raise HTTPException(403, 'Forbidden')
    db = get_db()
    body = await request.json()
    body.pop('_id', None)
    body.pop('id', None)
    body.pop('buyer_account', None)
    await db.buyers.update_one({'id': bid}, {'$set': {**body, 'updated_at': now()}})
    if body.get('buyer_name'):
        await db.users.update_one({'buyer_id': bid}, {'$set': {'name': body['buyer_name'], 'customer_name': body['buyer_name'], 'updated_at': now()}})
    await log_activity(user['id'], user['name'], 'Update', 'Buyers', f"Updated buyer: {bid}")
    return serialize_doc(await db.buyers.find_one({'id': bid}, {'_id': 0}))

@router.delete("/buyers/{bid}")
async def delete_buyer(bid: str, request: Request):
    user = await require_auth(request)
    if user.get('role') != 'superadmin':
        raise HTTPException(403, 'Forbidden')
    db = get_db()
    doc = await db.buyers.find_one({'id': bid})
    if not doc:
        raise HTTPException(404, 'Not found')
    await db.users.delete_many({'buyer_id': bid})
    await db.buyers.delete_one({'id': bid})
    await log_activity(user['id'], user['name'], 'Delete', 'Buyers', f"Deleted buyer: {doc.get('buyer_name')}")
    return {'success': True}

# ─── PRODUCTS ────────────────────────────────────────────────────────────────
# [DEPRECATED] Legacy `products` / `product_variants` collections. Superseded by
# rahaza_models (Internal) and buyer-catalog (Maklon). Kept for backward-compat only.
logger.info(
    "[DEPRECATION] /api/products/* and /api/product-variants/* (master_data) are "
    "DEPRECATED — superseded by /api/rahaza/models/* (Internal) and "
    "/api/dewi/maklon/buyer-catalog/* (Maklon). Kept for backward-compat/migration only."
)

@router.get("/products")
async def get_products(request: Request):
    await require_auth(request)
    db = get_db()
    sp = request.query_params
    query = {}
    search = sp.get('search')
    if search:
        query['$or'] = [{'product_name': {'$regex': re.escape(search), '$options': 'i'}}, {'product_code': {'$regex': re.escape(search), '$options': 'i'}}]
    return serialize_doc(await db.products.find(query, {'_id': 0}).sort('created_at', -1).to_list(500))

@router.get("/products/{pid}")
async def get_product(pid: str, request: Request):
    await require_auth(request)
    db = get_db()
    p = await db.products.find_one({'id': pid}, {'_id': 0})
    if not p:
        raise HTTPException(404, 'Not found')
    variants = await db.product_variants.find({'product_id': pid}, {'_id': 0}).sort('created_at', 1).to_list(500)
    result = serialize_doc(p)
    result['variants'] = serialize_doc(variants)
    return result

@router.post("/products")
async def create_product(request: Request):
    user = await require_auth(request)
    if not check_role(user, ['admin']):
        raise HTTPException(403, 'Forbidden')
    db = get_db()
    body = await request.json()
    product = {'id': new_id(), **body, 'status': body.get('status', 'active'), 'photo_url': '', 'created_at': now(), 'updated_at': now()}
    await db.products.insert_one(product)
    await log_activity(user['id'], user['name'], 'Create', 'Products', f"Created product: {product.get('product_name')}")
    return JSONResponse(serialize_doc(product), status_code=201)

@router.put("/products/{pid}")
async def update_product(pid: str, request: Request):
    user = await require_auth(request)
    if not check_role(user, ['admin']):
        raise HTTPException(403, 'Forbidden')
    db = get_db()
    body = await request.json()
    body.pop('_id', None)
    body.pop('id', None)
    await db.products.update_one({'id': pid}, {'$set': {**body, 'updated_at': now()}})
    await log_activity(user['id'], user['name'], 'Update', 'Products', f"Updated product: {pid}")
    return serialize_doc(await db.products.find_one({'id': pid}, {'_id': 0}))

@router.delete("/products/{pid}")
async def delete_product(pid: str, request: Request):
    user = await require_auth(request)
    if user.get('role') != 'superadmin':
        raise HTTPException(403, 'Forbidden')
    db = get_db()
    doc = await db.products.find_one({'id': pid})
    if not doc:
        raise HTTPException(404, 'Not found')
    await db.products.delete_one({'id': pid})
    await db.product_variants.delete_many({'product_id': pid})
    await log_activity(user['id'], user['name'], 'Delete', 'Products', f"Deleted product: {doc.get('product_name')}")
    return {'success': True}

@router.post("/products/{pid}/photo")
async def upload_product_photo(pid: str, request: Request, file: UploadFile = File(...)):
    user = await require_auth(request)
    if not check_role(user, ['admin']):
        raise HTTPException(403, 'Forbidden')
    db = get_db()
    product = await db.products.find_one({'id': pid})
    if not product:
        raise HTTPException(404, 'Product not found')
    content = await file.read()
    if len(content) > 5 * 1024 * 1024:
        raise HTTPException(400, 'File terlalu besar (maks 5MB)')
    ext = (file.filename or '').rsplit('.', 1)[-1].lower() if file.filename else 'jpg'
    if ext not in ('jpg', 'jpeg', 'png', 'webp', 'gif'):
        raise HTTPException(400, 'Format tidak didukung')
    content_type = file.content_type or f'image/{ext}'

    # Try Object Storage first; fallback to base64 if storage unavailable.
    photo_url = None
    storage_path = None
    try:
        from storage import put_object, generate_storage_path
        storage_path = generate_storage_path(f"products/{pid}", file.filename or f"photo.{ext}")
        put_object(storage_path, content, content_type)
        # Served via /api/file/by-path/<path> (see file_storage.py) or direct static endpoint
        photo_url = f"/api/products/{pid}/photo-stream"
    except Exception as e:
        import base64
        import logging
        logging.getLogger(__name__).warning(f"Object storage unavailable, fallback base64: {e}")
        b64 = base64.b64encode(content).decode('utf-8')
        photo_url = f"data:{content_type};base64,{b64}"

    update = {'photo_url': photo_url, 'updated_at': now()}
    if storage_path:
        update['photo_storage_path'] = storage_path
        update['photo_content_type'] = content_type
    await db.products.update_one({'id': pid}, {'$set': update})
    return {'success': True, 'photo_url': photo_url}


@router.get("/products/{pid}/photo-stream")
async def stream_product_photo(pid: str, request: Request):
    """Serve product photo from Object Storage. Accepts Authorization header OR ?token= query param."""
    from fastapi.responses import Response
    token_qs = request.query_params.get("token")
    if token_qs and not request.headers.get("authorization"):
        import jwt as _jwt
        import os as _os
        try:
            JWT_SECRET = _os.environ.get('JWT_SECRET', 'garment_erp_jwt_secret_2025')
            _jwt.decode(token_qs, JWT_SECRET, algorithms=['HS256'])
        except Exception:
            raise HTTPException(401, "Invalid token")
    else:
        await require_auth(request)
    db = get_db()
    product = await db.products.find_one({'id': pid}, {'_id': 0})
    if not product:
        raise HTTPException(404, 'Product not found')
    path = product.get('photo_storage_path')
    if not path:
        raise HTTPException(404, 'Photo not stored in object storage')
    try:
        from storage import get_object
        data, content_type = get_object(path)
        return Response(content=data, media_type=content_type, headers={"Cache-Control": "private, max-age=3600"})
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"photo stream error: {e}")
        raise HTTPException(500, 'Photo fetch failed')


# ─── PRODUCT VARIANTS ────────────────────────────────────────────────────────
@router.get("/product-variants")
async def get_variants(request: Request):
    await require_auth(request)
    db = get_db()
    query = {}
    pid = request.query_params.get('product_id')
    if pid:
        query['product_id'] = pid
    return serialize_doc(await db.product_variants.find(query, {'_id': 0}).sort('created_at', 1).to_list(500))

@router.get("/product-variants/{vid}")
async def get_variant(vid: str, request: Request):
    await require_auth(request)
    db = get_db()
    v = await db.product_variants.find_one({'id': vid}, {'_id': 0})
    if not v:
        raise HTTPException(404, 'Not found')
    return serialize_doc(v)

@router.post("/product-variants")
async def create_variant(request: Request):
    user = await require_auth(request)
    if not check_role(user, ['admin']):
        raise HTTPException(403, 'Forbidden')
    db = get_db()
    body = await request.json()
    product = await db.products.find_one({'id': body.get('product_id')})
    if not product:
        raise HTTPException(404, 'Product not found')
    variant = {
        'id': new_id(), 'product_id': body['product_id'],
        'product_code': product.get('product_code', ''), 'product_name': product.get('product_name', ''),
        'size': body.get('size', ''), 'color': body.get('color', ''), 'sku': body.get('sku', ''),
        'status': 'active', 'created_at': now()
    }
    await db.product_variants.insert_one(variant)
    await log_activity(user['id'], user['name'], 'Create', 'Product Variants', f"Added variant SKU: {body.get('sku')}")
    return JSONResponse(serialize_doc(variant), status_code=201)

@router.put("/product-variants/{vid}")
async def update_variant(vid: str, request: Request):
    user = await require_auth(request)
    if not check_role(user, ['admin']):
        raise HTTPException(403, 'Forbidden')
    db = get_db()
    body = await request.json()
    body.pop('_id', None)
    body.pop('id', None)
    await db.product_variants.update_one({'id': vid}, {'$set': {**body, 'updated_at': now()}})
    return serialize_doc(await db.product_variants.find_one({'id': vid}, {'_id': 0}))

@router.delete("/product-variants/{vid}")
async def delete_variant(vid: str, request: Request):
    user = await require_auth(request)
    if user.get('role') != 'superadmin':
        raise HTTPException(403, 'Forbidden')
    db = get_db()
    doc = await db.product_variants.find_one({'id': vid})
    if not doc:
        raise HTTPException(404, 'Not found')
    await db.product_variants.delete_one({'id': vid})
    await log_activity(user['id'], user['name'], 'Delete', 'Product Variants', f"Deleted variant: {doc.get('sku', vid)}")
    return {'success': True}

