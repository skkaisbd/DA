"""
Vendor CMT Portal — CV. Dewi Aditya ERP
========================================
Endpoints untuk vendor CMT (sub-kontraktor jahit) agar dapat:
  1. Melihat daftar pekerjaan yang ditugaskan ke mereka
  2. Submit progress harian per pekerjaan
  3. Melihat riwayat progress mereka sendiri

Admin dapat:
  1. Membuat & mengelola vendor partner (entitas vendor)
  2. Membuat & mengelola akun user vendor (role=cmt_vendor)
  3. Melihat semua job & progress lintas vendor

Koleksi baru (additive, tidak ubah koleksi existing):
  vendor_partners        : entitas vendor (nama, kontak)
  vendor_jobs            : pekerjaan yang diassign ke vendor
  vendor_progress_reports: laporan progress dari vendor

Route prefix: /api/vendor-portal
"""

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field
from datetime import datetime, timezone
from database import get_db
from auth import require_auth, serialize_doc, log_activity, hash_password, check_role
from utils.counters import next_counter, gen_prefixed_number
import uuid

# ── FASE 7 DEPRECATION (audit 2026-07-31, cacat CRIT CMT-1) ──────────────────
# Modul ini adalah PORTAL VENDOR LAMA dengan model data SENDIRI
# (`vendor_jobs` + `vendor_progress_reports`) yang TIDAK tersambung ke PO,
# dispatch, maupun tagihan. Terbukti: 0 dokumen di kedua collection, sementara
# pekerjaan nyata ada di `production_jobs`/`production_progress`. Progress yang
# diisi vendor di modul ini TIDAK berpengaruh apa pun — jebakan berbahaya.
#
# SSOT portal vendor = `routes/production_execution.py`
#   (`/api/production-jobs`, `/api/production-job-items`, `/api/production-progress`)
# dipakai oleh `frontend/src/components/erp/engine/VendorPortalApp.jsx`
# (portal yang benar-benar dibuka saat login role `cmt_vendor`).
#
# Endpoint di bawah DIPERTAHANKAN sementara HANYA untuk kompatibilitas data lama
# dan diberi header peringatan. FE lama (`VendorPortalModule.jsx`) sudah dilepas
# dari `moduleRegistry.js`. Jangan menambah fitur di sini.
DEPRECATED_NOTICE = (
    "Portal vendor lama (vendor_jobs) sudah dipensiunkan. Gunakan "
    "/api/production-jobs · /api/production-job-items · /api/production-progress "
    "(SSOT). Lihat docs/AUDIT_PRODUKSI_MAKLON_CMT.md §CMT-1."
)


router = APIRouter(prefix='/api/vendor-portal', tags=['Vendor-Portal'])
logger = __import__('logging').getLogger(__name__)


# ── Helpers ──────────────────────────────────────────────────────────────────

def _now(): return datetime.now(timezone.utc)
def _uid(): return str(uuid.uuid4())

def _require_admin(user: dict):
    if not check_role(user, ['admin', 'superadmin', 'owner', 'manager', 'ppic']):
        raise HTTPException(403, "Hanya admin yang dapat mengakses endpoint ini.")

def _require_vendor(user: dict):
    if user.get('role') != 'cmt_vendor':
        raise HTTPException(403, "Hanya akun vendor yang dapat mengakses endpoint ini.")

def _get_vendor_partner_id(user: dict) -> str:
    vid = user.get('cmt_vendor_id') or ''
    if not vid:
        raise HTTPException(403, "Akun vendor belum terhubung ke partner. Hubungi admin.")
    return vid


# ── Models ────────────────────────────────────────────────────────────────────

class PartnerIn(BaseModel):
    name:         str
    code:         str = ''
    contact_name: str = ''
    contact_phone:str = ''
    address:      str = ''
    notes:        str = ''
    is_active:    bool | None = None   # dipakai PUT untuk reactivate/deactivate (I-VP-5); create selalu True
    # M3 KAPASITAS (Maklon CMT Operasional Fase 4) — field additif di vendor_partners (SSOT master CMT).
    # capacity_pcs = kapasitas jahit maksimum (pcs) yang bisa ditangani vendor pada satu waktu.
    capacity_pcs:  int | None = Field(default=None, ge=0)
    capacity_note: str | None = None

class VendorAccountIn(BaseModel):
    email:      str
    name:       str
    password:   str
    partner_id: str  # harus ada partner dulu

class VendorJobIn(BaseModel):
    title:      str               # cth: "Jahit Kemeja Batik - 500 pcs"
    partner_id: str
    wo_id:      str = ''
    wo_number:  str = ''
    model_id:   str = ''          # link ke rahaza_models (untuk Panduan Produksi/SOP)
    qty_target: int = Field(ge=0, default=0)
    due_date:   str = ''
    process:    str = 'SEWING'    # SEWING | FINISHING | QC | EMBROIDERY | ...
    notes:      str = ''

class ProgressIn(BaseModel):
    qty_done:    int = Field(ge=0)
    qty_reject:  int = Field(default=0, ge=0)
    report_date: str = ''         # YYYY-MM-DD, default today
    process_step:str = ''         # tahap spesifik jika berbeda dari job.process
    notes:       str = ''


class VendorAccountUpdate(BaseModel):
    name:       str | None = None
    is_active:  bool | None = None
    partner_id: str | None = None
    password:   str | None = None   # opsional: reset password bila diisi


class VendorJobUpdate(BaseModel):
    title:      str | None = None
    partner_id: str | None = None
    model_id:   str | None = None
    qty_target: int | None = Field(default=None, ge=0)
    due_date:   str | None = None
    process:    str | None = None
    status:     str | None = None   # open | in_progress | done | cancelled
    notes:      str | None = None


# ── Startup index ──────────────────────────────────────────────────────────────

async def create_vendor_portal_indexes():
    db = get_db()
    await db.vendor_partners.create_index('code', unique=True, sparse=True)
    await db.vendor_jobs.create_index('partner_id')
    await db.vendor_jobs.create_index('job_number')
    await db.vendor_progress_reports.create_index([('job_id', 1), ('report_date', -1)])
    await db.vendor_progress_reports.create_index('partner_id')


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  ADMIN ENDPOINTS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# ── Partners ──────────────────────────────────────────────────────────────────

@router.get('/partners')
async def list_partners(request: Request):
    user = await require_auth(request)
    _require_admin(user)
    db = get_db()
    docs = await db.vendor_partners.find({}, {'_id': 0}).sort('name', 1).to_list(500)
    # Tambahkan stats per partner
    for p in docs:
        p['job_count']    = await db.vendor_jobs.count_documents({'partner_id': p['id']})
        p['account_count']= await db.users.count_documents({'cmt_vendor_id': p['id']})
    return serialize_doc(docs)


@router.post('/partners')
async def create_partner(payload: PartnerIn, request: Request):
    user = await require_auth(request)
    _require_admin(user)
    db = get_db()
    if payload.code:
        if await db.vendor_partners.find_one({'code': payload.code.upper()}):
            raise HTTPException(400, f"Kode vendor '{payload.code}' sudah digunakan.")
    doc = {
        'id':            _uid(),
        'name':          payload.name.strip(),
        'code':          payload.code.upper().strip() if payload.code else '',
        'contact_name':  payload.contact_name,
        'contact_phone': payload.contact_phone,
        'address':       payload.address,
        'notes':         payload.notes,
        'is_active':     True,
        'capacity_pcs':  int(payload.capacity_pcs) if payload.capacity_pcs is not None else 0,
        'capacity_note': payload.capacity_note or '',
        'created_at':    _now(),
        'created_by':    user['id'],
    }
    await db.vendor_partners.insert_one(doc)
    await log_activity(user['id'], user.get('name',''), f"create_vendor_partner:{doc['name']}", 'vendor_portal', doc['id'])
    return serialize_doc(doc)


@router.put('/partners/{partner_id}')
async def update_partner(partner_id: str, payload: PartnerIn, request: Request):
    user = await require_auth(request)
    _require_admin(user)
    db = get_db()
    partner = await db.vendor_partners.find_one({'id': partner_id})
    if not partner:
        raise HTTPException(404, "Partner tidak ditemukan.")
    # Kode boleh diubah, tapi harus tetap unik (abaikan diri sendiri)
    new_code = payload.code.upper().strip() if payload.code else ''
    if new_code and new_code != (partner.get('code') or ''):
        dup = await db.vendor_partners.find_one({'code': new_code, 'id': {'$ne': partner_id}})
        if dup:
            raise HTTPException(400, f"Kode vendor '{new_code}' sudah digunakan.")
    update = {
        'name':          payload.name.strip(),
        'code':          new_code,
        'contact_name':  payload.contact_name,
        'contact_phone': payload.contact_phone,
        'address':       payload.address,
        'notes':         payload.notes,
        'updated_at':    _now(),
    }
    if payload.is_active is not None:
        update['is_active'] = bool(payload.is_active)  # I-VP-5 (reactivate/deactivate)
    # M3 KAPASITAS — hanya update bila dikirim (non-destruktif untuk PUT lama yang tak kirim field ini)
    if payload.capacity_pcs is not None:
        update['capacity_pcs'] = int(payload.capacity_pcs)
    if payload.capacity_note is not None:
        update['capacity_note'] = payload.capacity_note
    await db.vendor_partners.update_one({'id': partner_id}, {'$set': update})
    await log_activity(user['id'], user.get('name',''), f"update_vendor_partner:{update['name']}", 'vendor_portal', partner_id)
    return {'ok': True}


@router.delete('/partners/{partner_id}')
async def delete_partner(partner_id: str, request: Request, hard: bool = Query(default=False)):
    """Nonaktifkan partner (soft, default) atau hapus permanen (?hard=true).

    Soft (I-VP-1/I-VP-2/I-VP-3): set is_active=false; diblokir bila masih ada
      AKUN AKTIF (is_active=true) atau JOB BERJALAN (status ∉ done/cancelled/completed).
    Hard: hapus dokumen; diblokir bila masih ada job/akun apa pun (integritas referensial).
    """
    user = await require_auth(request)
    _require_admin(user)
    db = get_db()
    partner = await db.vendor_partners.find_one({'id': partner_id})
    if not partner:
        raise HTTPException(404, "Partner tidak ditemukan.")
    if hard:
        job_count = await db.vendor_jobs.count_documents({'partner_id': partner_id})
        if job_count > 0:
            raise HTTPException(400, f"Tidak bisa hapus permanen: vendor masih punya {job_count} job. Hapus/batalkan job dulu.")
        acc_count = await db.users.count_documents({'cmt_vendor_id': partner_id})
        if acc_count > 0:
            raise HTTPException(400, f"Tidak bisa hapus permanen: vendor masih punya {acc_count} akun login. Hapus akun vendor dulu.")
        await db.vendor_partners.delete_one({'id': partner_id})
        await log_activity(user['id'], user.get('name',''), f"delete_vendor_partner:{partner.get('name','')}", 'vendor_portal', partner_id)
        return {'ok': True, 'deleted': True}
    # Soft deactivate — guard I-VP-1 (akun aktif) & I-VP-2 (job berjalan)
    active_acc = await db.users.count_documents(
        {'cmt_vendor_id': partner_id, 'role': 'cmt_vendor', 'is_active': True})
    active_job = await db.vendor_jobs.count_documents(
        {'partner_id': partner_id, 'status': {'$nin': ['done', 'cancelled', 'completed']}})
    if active_acc or active_job:
        raise HTTPException(400,
            f"Tidak bisa nonaktifkan: {active_acc} akun aktif & {active_job} job berjalan. "
            f"Nonaktifkan akun & selesaikan/batalkan job dulu.")
    await db.vendor_partners.update_one({'id': partner_id},
        {'$set': {'is_active': False, 'updated_at': _now()}})
    await log_activity(user['id'], user.get('name',''), f"deactivate_vendor_partner:{partner.get('name','')}", 'vendor_portal', partner_id)
    return {'ok': True, 'deleted': False}


# ── Vendor Accounts ────────────────────────────────────────────────────────────

@router.get('/accounts')
async def list_vendor_accounts(request: Request):
    user = await require_auth(request)
    _require_admin(user)
    db = get_db()
    users = await db.users.find({'role': 'cmt_vendor'}, {'_id': 0, 'password': 0}).sort('name', 1).to_list(500)
    # Enrich dengan nama partner
    partner_ids = {u.get('cmt_vendor_id') for u in users if u.get('cmt_vendor_id')}
    partner_map = {}
    if partner_ids:
        async for p in db.vendor_partners.find({'id': {'$in': list(partner_ids)}}, {'_id': 0, 'id': 1, 'name': 1}):
            partner_map[p['id']] = p['name']
    for u in users:
        u['partner_name'] = partner_map.get(u.get('cmt_vendor_id'), '—')
    return serialize_doc(users)


@router.post('/accounts')
async def create_vendor_account(payload: VendorAccountIn, request: Request):
    user = await require_auth(request)
    _require_admin(user)
    db = get_db()
    # Cek partner exists
    partner = await db.vendor_partners.find_one({'id': payload.partner_id})
    if not partner:
        raise HTTPException(400, "Partner ID tidak ditemukan. Buat partner dulu.")
    # Cek email unik
    if await db.users.find_one({'email': payload.email.lower()}):
        raise HTTPException(400, f"Email '{payload.email}' sudah terdaftar.")
    doc = {
        'id':             _uid(),
        'email':          payload.email.lower().strip(),
        'name':           payload.name.strip(),
        'password':       hash_password(payload.password),
        'role':           'cmt_vendor',
        'cmt_vendor_id':  payload.partner_id,
        'is_active':      True,
        'created_at':     _now(),
        'created_by':     user['id'],
    }
    await db.users.insert_one(doc)
    await log_activity(user['id'], user.get('name',''), f"create_vendor_account:{payload.email}", 'vendor_portal', doc['id'])
    safe = {k: v for k, v in doc.items() if k != 'password'}
    return serialize_doc(safe)


@router.put('/accounts/{account_id}')
async def update_vendor_account(account_id: str, payload: VendorAccountUpdate, request: Request):
    """Edit akun vendor: nama, status aktif, partner, dan (opsional) reset password."""
    user = await require_auth(request)
    _require_admin(user)
    db = get_db()
    acc = await db.users.find_one({'id': account_id, 'role': 'cmt_vendor'})
    if not acc:
        raise HTTPException(404, "Akun vendor tidak ditemukan.")
    update: dict = {'updated_at': _now()}
    if payload.name is not None and payload.name.strip():
        update['name'] = payload.name.strip()
    if payload.is_active is not None:
        update['is_active'] = bool(payload.is_active)
    if payload.partner_id is not None and payload.partner_id:
        partner = await db.vendor_partners.find_one({'id': payload.partner_id})
        if not partner:
            raise HTTPException(400, "Partner ID tidak ditemukan.")
        update['cmt_vendor_id'] = payload.partner_id
    if payload.password:
        if len(payload.password) < 6:
            raise HTTPException(400, "Password minimal 6 karakter.")
        update['password'] = hash_password(payload.password)
    await db.users.update_one({'id': account_id}, {'$set': update})
    await log_activity(user['id'], user.get('name',''), f"update_vendor_account:{acc.get('email','')}", 'vendor_portal', account_id)
    return {'ok': True, 'password_reset': bool(payload.password)}


@router.delete('/accounts/{account_id}')
async def delete_vendor_account(account_id: str, request: Request, hard: bool = Query(default=False)):
    """Nonaktifkan (default) atau hapus permanen (?hard=true) akun vendor."""
    user = await require_auth(request)
    _require_admin(user)
    db = get_db()
    acc = await db.users.find_one({'id': account_id, 'role': 'cmt_vendor'})
    if not acc:
        raise HTTPException(404, "Akun vendor tidak ditemukan.")
    if hard:
        await db.users.delete_one({'id': account_id})
        await log_activity(user['id'], user.get('name',''), f"delete_vendor_account:{acc.get('email','')}", 'vendor_portal', account_id)
        return {'ok': True, 'deleted': True}
    await db.users.update_one({'id': account_id}, {'$set': {'is_active': False, 'updated_at': _now()}})
    await log_activity(user['id'], user.get('name',''), f"deactivate_vendor_account:{acc.get('email','')}", 'vendor_portal', account_id)
    return {'ok': True, 'deleted': False}


# ── Jobs (admin view) ──────────────────────────────────────────────────────────

@router.get('/jobs')
async def list_all_jobs(
    request: Request,
    partner_id: str = Query(default=''),
    status:     str = Query(default=''),
):
    user = await require_auth(request)
    _require_admin(user)
    db = get_db()
    filt: dict = {}
    if partner_id:
        filt['partner_id'] = partner_id
    if status:
        filt['status'] = status
    jobs = await db.vendor_jobs.find(filt, {'_id': 0}).sort('created_at', -1).to_list(500)
    return serialize_doc(jobs)


@router.post('/jobs')
async def create_job(payload: VendorJobIn, request: Request):
    user = await require_auth(request)
    _require_admin(user)
    db = get_db()
    partner = await db.vendor_partners.find_one({'id': payload.partner_id})
    if not partner:
        raise HTTPException(400, "Partner ID tidak ditemukan.")
    # Resolve model (opsional) untuk Panduan Produksi/SOP
    model_code, model_name = '', ''
    if payload.model_id:
        mdl = await db.rahaza_models.find_one({'id': payload.model_id}, {'_id': 0, 'code': 1, 'name': 1})
        if mdl:
            model_code = mdl.get('code', '')
            model_name = mdl.get('name', '')
    job_number = await gen_prefixed_number(db, 'vendor_jobs', 'job_number', 'VJ-', 5)
    doc = {
        'id':          _uid(),
        'job_number':  job_number,
        'title':       payload.title.strip(),
        'partner_id':  payload.partner_id,
        'partner_name': partner.get('name', ''),
        'wo_id':       payload.wo_id,
        'wo_number':   payload.wo_number,
        'model_id':    payload.model_id,
        'model_code':  model_code,
        'model_name':  model_name,
        'qty_target':  payload.qty_target,
        'qty_done':    0,
        'due_date':    payload.due_date,
        'process':     payload.process.upper(),
        'notes':       payload.notes,
        'status':      'open',      # open | in_progress | done | cancelled
        'created_at':  _now(),
        'created_by':  user['id'],
    }
    await db.vendor_jobs.insert_one(doc)
    await log_activity(user['id'], user.get('name',''), f"create_vendor_job:{doc['job_number']}", 'vendor_portal', doc['id'])
    return serialize_doc(doc)


@router.put('/jobs/{job_id}')
async def update_job(job_id: str, payload: VendorJobUpdate, request: Request):
    """Edit job vendor. Bila partner/model diubah, nama turunan disinkronkan ulang."""
    user = await require_auth(request)
    _require_admin(user)
    db = get_db()
    job = await db.vendor_jobs.find_one({'id': job_id})
    if not job:
        raise HTTPException(404, "Job tidak ditemukan.")
    update: dict = {'updated_at': _now()}
    if payload.title is not None and payload.title.strip():
        update['title'] = payload.title.strip()
    if payload.partner_id is not None and payload.partner_id and payload.partner_id != job.get('partner_id'):
        partner = await db.vendor_partners.find_one({'id': payload.partner_id})
        if not partner:
            raise HTTPException(400, "Partner ID tidak ditemukan.")
        update['partner_id']   = payload.partner_id
        update['partner_name'] = partner.get('name', '')
    if payload.model_id is not None:
        update['model_id'] = payload.model_id
        if payload.model_id:
            mdl = await db.rahaza_models.find_one({'id': payload.model_id}, {'_id': 0, 'code': 1, 'name': 1})
            update['model_code'] = mdl.get('code', '') if mdl else ''
            update['model_name'] = mdl.get('name', '') if mdl else ''
        else:
            update['model_code'] = ''
            update['model_name'] = ''
    if payload.qty_target is not None:
        update['qty_target'] = int(payload.qty_target)
    if payload.due_date is not None:
        update['due_date'] = payload.due_date
    if payload.process is not None and payload.process.strip():
        update['process'] = payload.process.upper()
    if payload.notes is not None:
        update['notes'] = payload.notes
    if payload.status is not None and payload.status:
        if payload.status not in ('open', 'in_progress', 'done', 'cancelled'):
            raise HTTPException(400, "Status tidak valid.")
        update['status'] = payload.status
    await db.vendor_jobs.update_one({'id': job_id}, {'$set': update})
    await log_activity(user['id'], user.get('name',''), f"update_vendor_job:{job.get('job_number','')}", 'vendor_portal', job_id)
    return {'ok': True}


@router.delete('/jobs/{job_id}')
async def delete_job(job_id: str, request: Request):
    """Hapus job vendor. Diblokir bila sudah ada laporan progress (pakai status 'cancelled')."""
    user = await require_auth(request)
    _require_admin(user)
    db = get_db()
    job = await db.vendor_jobs.find_one({'id': job_id})
    if not job:
        raise HTTPException(404, "Job tidak ditemukan.")
    prog_count = await db.vendor_progress_reports.count_documents({'job_id': job_id})
    if prog_count > 0:
        raise HTTPException(400, f"Tidak bisa hapus: job punya {prog_count} laporan progress. Batalkan job (ubah status ke 'cancelled') sebagai gantinya.")
    await db.vendor_jobs.delete_one({'id': job_id})
    await log_activity(user['id'], user.get('name',''), f"delete_vendor_job:{job.get('job_number','')}", 'vendor_portal', job_id)
    return {'ok': True}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  VENDOR SELF-SERVICE ENDPOINTS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.get('/me')
async def vendor_me(request: Request):
    """Profil vendor yang sedang login."""
    user = await require_auth(request)
    _require_vendor(user)
    db = get_db()
    partner_id = user.get('cmt_vendor_id', '')
    partner    = None
    if partner_id:
        partner = await db.vendor_partners.find_one({'id': partner_id}, {'_id': 0})
    return serialize_doc({
        'id':     user['id'],
        'name':   user.get('name', ''),
        'email':  user.get('email', ''),
        'role':   user.get('role', ''),
        'partner': serialize_doc(partner) if partner else None,
    })


@router.get('/my-jobs')
async def vendor_my_jobs(
    request: Request,
    status: str = Query(default=''),
):
    """Daftar pekerjaan yang ditugaskan ke vendor ini."""
    user = await require_auth(request)
    _require_vendor(user)
    partner_id = _get_vendor_partner_id(user)
    db = get_db()
    filt: dict = {'partner_id': partner_id}
    if status:
        filt['status'] = status
    jobs = await db.vendor_jobs.find(filt, {'_id': 0}).sort('created_at', -1).to_list(200)
    # Tambah total progress per job
    for j in jobs:
        total = await db.vendor_progress_reports.aggregate([
            {'$match': {'job_id': j['id']}},
            {'$group': {'_id': None, 'total_done': {'$sum': '$qty_done'}, 'total_reject': {'$sum': '$qty_reject'}}},
        ]).to_list(1)
        j['reported_qty_done']   = total[0]['total_done']   if total else 0
        j['reported_qty_reject'] = total[0]['total_reject'] if total else 0
    return serialize_doc(jobs)


@router.get('/my-jobs/{job_id}')
async def vendor_job_detail(job_id: str, request: Request):
    """Detail satu pekerjaan milik vendor."""
    user = await require_auth(request)
    _require_vendor(user)
    partner_id = _get_vendor_partner_id(user)
    db = get_db()
    job = await db.vendor_jobs.find_one({'id': job_id, 'partner_id': partner_id}, {'_id': 0})
    if not job:
        raise HTTPException(404, "Pekerjaan tidak ditemukan atau bukan milik vendor ini.")
    # Progress summary
    total = await db.vendor_progress_reports.aggregate([
        {'$match': {'job_id': job_id}},
        {'$group': {'_id': None, 'total_done': {'$sum': '$qty_done'}, 'total_reject': {'$sum': '$qty_reject'}, 'report_count': {'$sum': 1}}},
    ]).to_list(1)
    job['reported_qty_done']   = total[0]['total_done']   if total else 0
    job['reported_qty_reject'] = total[0]['total_reject'] if total else 0
    job['report_count']        = total[0]['report_count'] if total else 0
    # Progress percentage
    target = job.get('qty_target', 0)
    job['progress_pct'] = round(job['reported_qty_done'] / target * 100, 1) if target > 0 else 0
    return serialize_doc(job)


@router.get('/my-jobs/{job_id}/production-guide')
async def vendor_job_production_guide(job_id: str, request: Request):
    """Panduan Produksi (SOP + foto + video) untuk model pada job vendor ini.
    Read-only & scoped: hanya job milik vendor yang login."""
    user = await require_auth(request)
    _require_vendor(user)
    partner_id = _get_vendor_partner_id(user)
    db = get_db()
    job = await db.vendor_jobs.find_one({'id': job_id, 'partner_id': partner_id}, {'_id': 0})
    if not job:
        raise HTTPException(404, "Pekerjaan tidak ditemukan atau bukan milik vendor ini.")
    model = None
    if job.get('model_id'):
        model = await db.rahaza_models.find_one({'id': job['model_id']}, {'_id': 0})
    if not model:
        return {
            'has_model': False,
            'model': None,
            'message': 'Belum ada model produk yang ditautkan ke pekerjaan ini. '
                       'Hubungi admin/PPIC untuk melengkapi Panduan Produksi.',
        }
    m = serialize_doc(model)
    guide = {k: m.get(k) for k in (
        'id', 'code', 'name', 'category', 'description', 'image_paths',
        'sop_steps', 'reference_videos', 'reference_images', 'sop_updated_at', 'sop_updated_by',
    )}
    guide['image_paths'] = list(guide.get('image_paths') or [])
    guide['sop_steps'] = list(guide.get('sop_steps') or [])
    guide['reference_videos'] = list(guide.get('reference_videos') or [])
    guide['reference_images'] = list(guide.get('reference_images') or [])
    return {'has_model': True, 'model': guide}


@router.post('/my-jobs/{job_id}/progress')
async def vendor_submit_progress(job_id: str, payload: ProgressIn, request: Request):
    """Vendor submit progress harian untuk satu job."""
    user = await require_auth(request)
    _require_vendor(user)
    partner_id = _get_vendor_partner_id(user)
    db = get_db()
    # Verifikasi kepemilikan job
    job = await db.vendor_jobs.find_one({'id': job_id, 'partner_id': partner_id})
    if not job:
        raise HTTPException(404, "Pekerjaan tidak ditemukan atau bukan milik vendor ini.")
    if job.get('status') in ('done', 'cancelled'):
        raise HTTPException(400, f"Pekerjaan sudah berstatus '{job['status']}', tidak bisa update progress.")
    if payload.qty_done <= 0:
        raise HTTPException(400, "qty_done harus lebih dari 0.")
    if payload.qty_reject > payload.qty_done:
        raise HTTPException(400, "qty_reject tidak boleh melebihi qty_done.")
    report_date = payload.report_date or _now().date().isoformat()
    doc = {
        'id':           _uid(),
        'job_id':       job_id,
        'job_number':   job.get('job_number', ''),
        'partner_id':   partner_id,
        'qty_done':     payload.qty_done,
        'qty_reject':   payload.qty_reject,
        'qty_pass':     payload.qty_done - payload.qty_reject,
        'report_date':  report_date,
        'process_step': (payload.process_step or job.get('process', '')).upper(),
        'notes':        payload.notes,
        'submitted_by': user['id'],
        'submitted_name': user.get('name', ''),
        'submitted_at': _now(),
        'source':       'vendor_self_report',
    }
    await db.vendor_progress_reports.insert_one(doc)
    # Update job.qty_done (kumulatif) dan set status in_progress
    total_done = (await db.vendor_progress_reports.aggregate([
        {'$match': {'job_id': job_id}},
        {'$group': {'_id': None, 'total': {'$sum': '$qty_done'}}},
    ]).to_list(1))
    new_total = total_done[0]['total'] if total_done else doc['qty_done']
    target    = job.get('qty_target', 0)
    new_status = 'done' if (target > 0 and new_total >= target) else 'in_progress'
    await db.vendor_jobs.update_one({'id': job_id}, {'$set': {'qty_done': new_total, 'status': new_status, 'updated_at': _now()}})
    await log_activity(user['id'], user.get('name',''), f"vendor_progress:{job['job_number']}:qty={payload.qty_done}", 'vendor_portal', job_id)
    return serialize_doc({**doc, 'job_status': new_status, 'cumulative_done': new_total})


@router.get('/my-jobs/{job_id}/progress-history')
async def vendor_progress_history(job_id: str, request: Request):
    """Riwayat progress yang sudah disubmit vendor untuk satu job."""
    user = await require_auth(request)
    _require_vendor(user)
    partner_id = _get_vendor_partner_id(user)
    db = get_db()
    # Verifikasi kepemilikan
    if not await db.vendor_jobs.find_one({'id': job_id, 'partner_id': partner_id}):
        raise HTTPException(404, "Pekerjaan tidak ditemukan.")
    reports = await db.vendor_progress_reports.find(
        {'job_id': job_id}, {'_id': 0}
    ).sort('submitted_at', -1).to_list(200)
    return serialize_doc(reports)


@router.delete('/my-jobs/{job_id}/progress/{report_id}')
async def vendor_delete_progress(job_id: str, report_id: str, request: Request):
    """Hapus 1 entry progress (hanya entry hari ini & milik sendiri)."""
    user = await require_auth(request)
    _require_vendor(user)
    partner_id = _get_vendor_partner_id(user)
    db = get_db()
    report = await db.vendor_progress_reports.find_one({'id': report_id, 'job_id': job_id, 'partner_id': partner_id})
    if not report:
        raise HTTPException(404, "Progress tidak ditemukan.")
    # Hanya boleh hapus entry hari ini
    today = _now().date().isoformat()
    if report.get('report_date') != today:
        raise HTTPException(400, "Hanya bisa menghapus progress yang diinput hari ini.")
    await db.vendor_progress_reports.delete_one({'id': report_id})
    # Recalculate cumulative
    total = await db.vendor_progress_reports.aggregate([
        {'$match': {'job_id': job_id}},
        {'$group': {'_id': None, 'total': {'$sum': '$qty_done'}}},
    ]).to_list(1)
    new_total = total[0]['total'] if total else 0
    job = await db.vendor_jobs.find_one({'id': job_id})
    target = job.get('qty_target', 0) if job else 0
    new_status = 'done' if (target > 0 and new_total >= target) else ('in_progress' if new_total > 0 else 'open')
    await db.vendor_jobs.update_one({'id': job_id}, {'$set': {'qty_done': new_total, 'status': new_status}})
    return {'ok': True}


# ── Admin: Progress History semua vendor ──────────────────────────────────────

@router.get('/progress-audit')
async def admin_progress_audit(
    request: Request,
    partner_id: str = Query(default=''),
    date_from:  str = Query(default=''),
    date_to:    str = Query(default=''),
    limit:      int = Query(default=100, ge=1, le=500),
):
    """Admin: Lihat semua progress report dari semua vendor."""
    user = await require_auth(request)
    _require_admin(user)
    db = get_db()
    filt: dict = {}
    if partner_id:
        filt['partner_id'] = partner_id
    if date_from:
        filt.setdefault('report_date', {})['$gte'] = date_from
    if date_to:
        filt.setdefault('report_date', {})['$lte'] = date_to
    reports = await db.vendor_progress_reports.find(filt, {'_id': 0}).sort('submitted_at', -1).to_list(limit)
    return serialize_doc(reports)
