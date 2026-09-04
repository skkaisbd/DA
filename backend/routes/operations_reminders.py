"""
operations_reminders.py — Vendor Reminder Management
Endpoints: /api/reminders/*

Refactored: Session #12 P2 (split from operations.py 2580 LOC monolith,
deprecated accessories section removed)
"""
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse
from database import get_db
from auth import require_auth, check_role, log_activity, serialize_doc
from routes.shared import new_id, now

router = APIRouter(prefix="/api", tags=["reminders"])

@router.get("/reminders")
async def get_reminders(request: Request):
    """Inbox reminder vendor (modul 11 dari 11).

    ── KEBOCORAN DATA yang ditutup (2026-08-08) ─────────────────────────────
    Scoping-nya dulu `if user.get('role') == 'vendor'` — role portal CMT yang
    sebenarnya adalah **`cmt_vendor`**, jadi setiap vendor CMT yang login melihat
    reminder MILIK SEMUA VENDOR. Sekarang scoping memakai SSOT
    `production_rbac.is_vendor()` (mencakup `vendor` + `cmt_vendor`) dan
    mendukung mode Portal CMT Override untuk staf DA.
    """
    user = await require_auth(request)
    db = get_db()
    from routes.production_rbac import is_vendor
    from core.cmt_override import apply_scope
    query = {}
    sp = request.query_params
    await apply_scope(request, user, db, query, param_vendor_id=sp.get('vendor_id'))
    if sp.get('status'):
        query['status'] = sp['status']
    reminders = await db.reminders.find(query, {'_id': 0}).sort('created_at', -1).to_list(500)
    # Bantu UI: tandai apakah pembaca ini boleh membalas (vendor / staf override).
    _can_reply = is_vendor(user) or bool(getattr(request.state, '_cmt_override_ctx', None))
    for r in reminders:
        r['can_reply'] = _can_reply
    return serialize_doc(reminders)

@router.post("/reminders")
async def create_reminder(request: Request):
    user = await require_auth(request)
    if not check_role(user, ['admin', 'admin_produksi', 'supervisor_produksi', 'ppic']):
        raise HTTPException(403, 'Forbidden')
    db = get_db()
    body = await request.json()
    vendor_id = body.get('vendor_id')
    if not vendor_id:
        raise HTTPException(400, 'vendor_id required')
    # Master vendor: `garments` (engine) ATAU `vendor_partners` (CMT DA).
    # Dulu hanya `garments` ⇒ reminder untuk vendor CMT selalu lahir tanpa nama.
    from routes.production_rbac import resolve_vendor_doc
    vendor = await resolve_vendor_doc(db, vendor_id)
    if not vendor:
        raise HTTPException(404, 'Vendor tidak ditemukan di master')
    reminder = {
        'id': new_id(),
        'vendor_id': vendor_id, 'vendor_name': (vendor or {}).get('garment_name', ''),
        'po_id': body.get('po_id', ''), 'po_number': body.get('po_number', ''),
        'reminder_type': body.get('reminder_type', 'general'),
        'subject': body.get('subject', ''), 'message': body.get('message', ''),
        'priority': body.get('priority', 'normal'),
        'status': 'pending', 'response': None, 'response_date': None,
        'created_by': user.get('name', ''), 'created_at': now(), 'updated_at': now()
    }
    await db.reminders.insert_one(reminder)
    await log_activity(user['id'], user.get('name', ''), 'create', 'reminder', f"Sent reminder to {(vendor or {}).get('garment_name', vendor_id)}")
    return JSONResponse(serialize_doc({k: v for k, v in reminder.items() if k != '_id'}), status_code=201)

@router.put("/reminders/{reminder_id}")
async def update_reminder(reminder_id: str, request: Request):
    """Balas / kelola reminder.

    ── BUG NYATA yang ditutup (2026-08-08) ──────────────────────────────────
    Jalur balasan dulu `if user.get('role') == 'vendor'` sehingga **vendor CMT
    (`cmt_vendor`) tidak pernah bisa membalas reminder** — tombol balas di
    VendorReminderInbox.jsx tersimpan tanpa efek apa pun (status tetap 'pending').
    Sekarang: semua role vendor (SSOT `is_vendor`) + staf DA dalam mode Portal
    CMT Override boleh membalas, dan balasan staf distempel jejak auditnya.
    """
    user = await require_auth(request)
    db = get_db()
    from routes.production_rbac import is_vendor, vendor_identity
    from core.cmt_override import resolve_override, stamp as ov_stamp
    body = await request.json()
    existing = await db.reminders.find_one({'id': reminder_id})
    if not existing:
        raise HTTPException(404, 'Reminder not found')
    _ov = await resolve_override(request, user, db)
    # Scoping: vendor & staf override hanya boleh menyentuh remindernya sendiri.
    if is_vendor(user) and existing.get('vendor_id') != vendor_identity(user):
        raise HTTPException(403, 'Reminder ini bukan milik vendor Anda')
    if _ov and existing.get('vendor_id') != _ov['vendor_id']:
        raise HTTPException(403, f"Reminder ini bukan milik {_ov['vendor_name']}")
    update = {'updated_at': now()}
    # Vendor responding — atau staf DA membalas ATAS NAMA vendor (mode override)
    if (is_vendor(user) or _ov) and body.get('response'):
        update['response'] = body['response']
        update['response_date'] = now()
        update['responded_by'] = user.get('name', '')
        update['status'] = 'responded'
        _stamp = ov_stamp(_ov)
        if _stamp:
            update.update({f'response_{k}': v for k, v in _stamp.items()})
    # Admin updating
    if check_role(user, ['admin', 'admin_produksi', 'supervisor_produksi', 'ppic']):
        if 'status' in body:
            update['status'] = body['status']
        if 'message' in body:
            update['message'] = body['message']
    await db.reminders.update_one({'id': reminder_id}, {'$set': update})
    return serialize_doc(await db.reminders.find_one({'id': reminder_id}, {'_id': 0}))

@router.delete("/reminders/{reminder_id}")
async def delete_reminder(reminder_id: str, request: Request):
    user = await require_auth(request)
    if not check_role(user, ['admin']):
        raise HTTPException(403, 'Forbidden')
    db = get_db()
    await db.reminders.delete_one({'id': reminder_id})
    return {'success': True}
