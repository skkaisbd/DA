import jwt
import bcrypt
import uuid
import os
import random
from datetime import datetime, timezone, timedelta
from fastapi import Request, HTTPException
from database import get_db
from dotenv import load_dotenv
from pathlib import Path
from bson import ObjectId

# Load .env so JWT_SECRET is available even if not set in supervisor environment
_ROOT_DIR = Path(__file__).parent
load_dotenv(_ROOT_DIR / '.env')

# H3 fix: No hardcoded fallback — raise KeyError fast if env is missing
JWT_SECRET = os.environ.get('JWT_SECRET')
if not JWT_SECRET:
    raise RuntimeError(
        "JWT_SECRET env var is required. Set it in .env before starting the server."
    )

def generate_password(length=10):
    chars = 'ABCDEFGHJKMNPQRSTUVWXYZabcdefghjkmnpqrstuvwxyz23456789@#!'
    return ''.join(random.choice(chars) for _ in range(length))

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt(10)).decode('utf-8')

def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))

def create_token(user_data: dict) -> str:
    payload = {
        'id':            user_data['id'],
        'email':         user_data['email'],
        'role':          user_data['role'],
        'name':          user_data['name'],
        'vendor_id':     user_data.get('vendor_id'),
        'buyer_id':      user_data.get('buyer_id'),
        'customer_name': user_data.get('customer_name', user_data.get('buyer_company', '')),
        'employee_id':   user_data.get('employee_id'),   # HR self-service linking
        'cmt_vendor_id': user_data.get('cmt_vendor_id'),  # CMT Vendor portal linking (Session #11.21)
        # 2026-08-07 — `department` IKUT di token. Sebelumnya tidak ada, sehingga
        # `user.get('department')` selalu kosong di seluruh backend dan setiap
        # aturan berbasis departemen (mis. batas departemen pada persetujuan PR)
        # diam-diam tidak pernah berjalan.
        'department':    user_data.get('department', ''),
        'exp':           datetime.now(timezone.utc) + timedelta(hours=24)
    }
    return jwt.encode(payload, JWT_SECRET, algorithm='HS256')

def verify_token(request: Request):
    auth_header = request.headers.get('Authorization', '')
    if not auth_header.startswith('Bearer '):
        return None
    try:
        token = auth_header.split(' ')[1]
        return jwt.decode(token, JWT_SECRET, algorithms=['HS256'])
    except Exception:
        return None

def verify_token_str(token: str):
    """Verify a raw JWT string (no Request object). Used for query-param auth."""
    if not token:
        return None
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=['HS256'])
    except Exception:
        return None

async def require_auth(request: Request):
    user = verify_token(request)
    if not user:
        raise HTTPException(status_code=401, detail='Unauthorized')
    # Pre-load permissions for custom roles
    role = user.get('role', '')
    if role == 'superadmin' or role == 'admin':
        user['_permissions'] = ['*']
        user['_role_perms'] = ['*']
    elif role == 'vendor':
        user['_permissions'] = ['dashboard.view', 'shipment.view', 'jobs.view', 'jobs.create', 'progress.view', 'progress.create']
        user['_role_perms'] = list(user['_permissions'])
    elif role == 'cmt_vendor':
        user['_permissions'] = ['cmt.my_jobs.view', 'cmt.progress.create', 'cmt.do.view']
        user['_role_perms'] = list(user['_permissions'])
    elif role == 'buyer':
        user['_permissions'] = ['dashboard.view', 'po.view', 'shipment.view']
        user['_role_perms'] = list(user['_permissions'])
    else:
        # Custom / legacy role: baca izin role + izin tambahan per orang.
        # `_role_perms` dipakai routes.shared.perms_configured() untuk memutuskan
        # apakah aturan role legacy masih dipakai (model "fallback aman").
        role_perms, extra_perms = await _load_rbac(role, user.get('id'))
        user['_role_perms'] = role_perms
        user['_extra_permissions'] = extra_perms
        user['_permissions'] = sorted(set(role_perms) | set(extra_perms))
    # Set user on request.state for routes that access it
    request.state.user = user
    return user


# ── Cache ringan izin RBAC (hindari 2 query per request) ─────────────────────
# TTL pendek supaya perubahan di layar "Peran & Hak Akses" cepat terasa; simpan
# juga hook invalidasi eksplisit yang dipanggil endpoint role (routes/admin.py).
_RBAC_TTL_SECONDS = 20
_rbac_cache: dict = {}


def bump_rbac_cache():
    """Kosongkan cache izin — dipanggil setelah role/permission diubah."""
    _rbac_cache.clear()


async def _load_rbac(role: str, user_id):
    key = (str(role or '').lower(), str(user_id or ''))
    hit = _rbac_cache.get(key)
    nowts = datetime.now(timezone.utc).timestamp()
    if hit and hit[0] > nowts:
        return list(hit[1]), list(hit[2])
    db = get_db()
    role_perms: list = []
    custom_role = await db.roles.find_one({'name': role}, {'_id': 0, 'id': 1})
    if custom_role:
        rows = await db.role_permissions.find(
            {'role_id': custom_role['id']}, {'_id': 0, 'permission_key': 1}
        ).to_list(1000)
        role_perms = sorted({rp.get('permission_key') for rp in rows if rp.get('permission_key')})
    extra_perms: list = []
    if user_id:
        udoc = await db.users.find_one({'id': user_id}, {'_id': 0, 'extra_permissions': 1})
        extra_perms = [p for p in ((udoc or {}).get('extra_permissions') or []) if p]
    _rbac_cache[key] = (nowts + _RBAC_TTL_SECONDS, role_perms, extra_perms)
    return list(role_perms), list(extra_perms)

def check_role(user: dict, allowed_roles: list, perm_key: str = None) -> bool:
    if user.get('role') == 'superadmin':
        return True
    if user.get('role') in allowed_roles:
        return True
    # Check custom role permissions loaded by require_auth
    perms = user.get('_permissions', [])
    if '*' in perms:
        return True
    if perm_key and perm_key in perms:
        return True
    # Don't grant access just because user has "any" permissions — only if specific perm_key matches
    return False

async def log_activity(user_id, user_name, action, module, details=''):
    db = get_db()
    await db.activity_logs.insert_one({
        'id': str(uuid.uuid4()),
        'user_id': user_id,
        'user_name': user_name,
        'action': action,
        'module': module,
        'details': details,
        'timestamp': datetime.now(timezone.utc)
    })

async def seed_initial_data():
    db = get_db()

    # Ensure superadmin
    admin = await db.users.find_one({'email': 'admin@garment.com'})
    if not admin:
        hashed = hash_password('Admin@123')
        await db.users.insert_one({
            'id': str(uuid.uuid4()),
            'name': 'Super Admin',
            'email': 'admin@garment.com',
            'password': hashed,
            'role': 'superadmin',
            'status': 'active',
            'created_at': datetime.now(timezone.utc),
            'updated_at': datetime.now(timezone.utc)
        })
        print('Superadmin seeded: admin@garment.com / Admin@123')

    # Seed default custom roles for CV. Dewi Aditya RBAC
    await _seed_default_roles(db)

    # Seed company profile placeholder (CV. Dewi Aditya Official)
    existing_co = await db.company_settings.find_one({})
    if not existing_co:
        await db.company_settings.insert_one({
            'id': str(uuid.uuid4()),
            'type': 'general',
            'company_name': 'CV. DEWI ADITYA OFFICIAL',
            'company_address': 'Sragen, Jawa Tengah',
            'company_tagline': 'Fashion Brand & Jasa Maklon Garment',
            'npwp': '',
            'company_phone': '',
            'company_email': '',
            'company_website': '',
            'company_logo_url': '',
            'pdf_header_line1': '',
            'pdf_header_line2': '',
            'pdf_footer_text': '',
            'created_at': datetime.now(timezone.utc),
            'updated_at': datetime.now(timezone.utc),
        })
        print('  · Company settings seeded')
    elif not existing_co.get('type'):
        # Migrasi drift: doc lama tanpa type → set type:'general' + map field lama.
        await db.company_settings.update_one(
            {'id': existing_co['id']},
            {'$set': {
                'type': 'general',
                'company_phone': existing_co.get('company_phone') or existing_co.get('phone', ''),
                'company_email': existing_co.get('company_email') or existing_co.get('email', ''),
                'company_website': existing_co.get('company_website', ''),
                'company_logo_url': existing_co.get('company_logo_url', ''),
                'pdf_header_line1': existing_co.get('pdf_header_line1', ''),
                'pdf_header_line2': existing_co.get('pdf_header_line2', ''),
                'pdf_footer_text': existing_co.get('pdf_footer_text', ''),
                'updated_at': datetime.now(timezone.utc),
            }},
        )
        print('  · Company settings migrated (type=general)')


async def _seed_default_roles(db):
    DEFAULT_ROLES = [
        # Produksi
        {'name': 'supervisor_produksi', 'description': 'Supervisor Produksi'},
        {'name': 'admin_produksi', 'description': 'Admin Produksi & PPIC'},
        {'name': 'operator', 'description': 'Operator Lantai'},
        {'name': 'spv_cuting', 'description': 'Supervisor Cutting'},
        {'name': 'operator_cuting', 'description': 'Operator Cutting'},
        {'name': 'rnd_staff', 'description': 'Staff RnD & Desain Produk'},
        # Gudang
        {'name': 'admin_gudang', 'description': 'Admin Gudang'},
        {'name': 'spv_packing', 'description': 'Supervisor Packing'},
        {'name': 'tim_packing', 'description': 'Tim Packing & QC'},
        {'name': 'admin_aksesoris', 'description': 'Admin Aksesoris'},
        # SDM
        {'name': 'hr', 'description': 'Tim SDM'},
        {'name': 'hr_manager', 'description': 'HR Manager'},
        # Keuangan
        {'name': 'accounting', 'description': 'Tim Keuangan'},
        {'name': 'staff_keuangan', 'description': 'Staff Keuangan'},
        # Maklon
        {'name': 'admin_maklon', 'description': 'Admin Maklon & Klien'},
        {'name': 'klien_maklon', 'description': 'Klien Maklon (View Only)'},
        # Toko Online
        {'name': 'pic_toko', 'description': 'PIC Toko & Marketplace'},
        {'name': 'marketing_kol', 'description': 'Marketing & KOL Specialist'},
        {'name': 'cs_staff', 'description': 'Customer Service'},
        # Legacy / Tetap
        {'name': 'owner', 'description': 'Owner/Pemilik'},
        {'name': 'supervisor', 'description': 'Supervisor (Legacy)'},
    ]
    for role_data in DEFAULT_ROLES:
        existing = await db.roles.find_one({'name': role_data['name']})
        if not existing:
            await db.roles.insert_one({
                'id': str(uuid.uuid4()),
                **role_data,
                'active': True,
                'created_at': datetime.now(timezone.utc),
            })

def serialize_doc(doc):
    """Recursively convert MongoDB documents to JSON-serializable format."""
    if isinstance(doc, list):
        return [serialize_doc(d) for d in doc]
    if isinstance(doc, dict):
        result = {}
        for k, v in doc.items():
            if k == '_id':
                continue
            result[k] = serialize_doc(v)
        return result
    if isinstance(doc, datetime):
        return doc.isoformat()
    if isinstance(doc, ObjectId):
        return str(doc)
    return doc
