# ruff: noqa: F401
"""
marketing_livehost_portal.py — LiveHost Self-Service Portal
Extracted from marketing_livehost.py (2278 LOC monolith)

Refactored: Session #11.19 Phase 3.2 Batch #2
Endpoints: POST /portal/auth/login, GET /portal/my-profile, GET /portal/my-shifts, GET /portal/scripts, GET /portal/training, POST /portal/training/{id}/complete, POST /portal/clock, GET /portal/notifications, GET /portal/notifications/stream, POST /portal/notifications/{id}/read, POST /portal/notifications/mark-all-read
"""
from fastapi import APIRouter, HTTPException, Request, Query, Path
from fastapi.responses import StreamingResponse
from database import get_db
from auth import require_auth, serialize_doc, log_activity
from routes.marketing_livehost_shared import (
    _uid, _now, _get_user, _create_livehost_token, _decode_livehost_token,
    require_livehost_auth, LiveHostCreate, LiveHostUpdate, ShiftCreate, ShiftUpdate,
    ClockInOut, ShiftPerformanceRecord, ScriptCreate, TrainingCreate, TrainingAssign,
    TrainingComplete, LiveHostLoginIn, UPLOAD_DIR, UUID_PATH_REGEX,
    _notif_insert_ssot, _reshape_lh_notif,
    PORTAL_LOGIN_ATTEMPTS, MAX_LOGIN_ATTEMPTS, LOCKOUT_DURATION_MINUTES,
    _livehost_sse_subscribers, publish_livehost_notification,
)
from auth import hash_password, verify_password
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, List
import json
import asyncio

_log = logging.getLogger(__name__)

router = APIRouter(prefix='/api/marketing/livehost', tags=['Marketing-LiveHost-Portal'])

@router.post('/portal/auth/login')
async def livehost_portal_login(data: LiveHostLoginIn, request: Request):
    """LiveHost login to their portal (separate from admin)"""
    db = get_db()
    
    # Brute-force protection
    client_ip = request.client.host if request.client else 'unknown'
    identifier = f"{client_ip}:{data.email.lower()}"
    
    # Check if locked
    if identifier in PORTAL_LOGIN_ATTEMPTS:
        attempt_data = PORTAL_LOGIN_ATTEMPTS[identifier]
        if attempt_data.get('locked_until') and _now() < attempt_data['locked_until']:
            remaining = int((attempt_data['locked_until'] - _now()).total_seconds() / 60)
            raise HTTPException(429, f'Terlalu banyak percobaan gagal. Coba lagi dalam {remaining} menit')
    
    # Find host
    host = await db.marketing_livehosts.find_one({'email': data.email.lower().strip()}, {'_id': 0})
    if not host or host.get('status') != 'active':
        # Track failed attempt
        if identifier not in PORTAL_LOGIN_ATTEMPTS:
            PORTAL_LOGIN_ATTEMPTS[identifier] = {'attempts': 0, 'first_attempt': _now()}
        PORTAL_LOGIN_ATTEMPTS[identifier]['attempts'] += 1
        PORTAL_LOGIN_ATTEMPTS[identifier]['last_attempt'] = _now()
        
        # Lock after 5 failed attempts
        if PORTAL_LOGIN_ATTEMPTS[identifier]['attempts'] >= 5:
            PORTAL_LOGIN_ATTEMPTS[identifier]['locked_until'] = _now() + timedelta(minutes=15)
        
        raise HTTPException(401, 'Email atau password salah')
    
    # Verify password
    if not verify_password(data.password, host.get('password_hash', '')):
        # Track failed attempt
        if identifier not in PORTAL_LOGIN_ATTEMPTS:
            PORTAL_LOGIN_ATTEMPTS[identifier] = {'attempts': 0, 'first_attempt': _now()}
        PORTAL_LOGIN_ATTEMPTS[identifier]['attempts'] += 1
        PORTAL_LOGIN_ATTEMPTS[identifier]['last_attempt'] = _now()
        
        if PORTAL_LOGIN_ATTEMPTS[identifier]['attempts'] >= 5:
            PORTAL_LOGIN_ATTEMPTS[identifier]['locked_until'] = _now() + timedelta(minutes=15)
        
        raise HTTPException(401, 'Email atau password salah')
    
    # Success - clear attempts
    if identifier in PORTAL_LOGIN_ATTEMPTS:
        del PORTAL_LOGIN_ATTEMPTS[identifier]
    
    # Update last login
    await db.marketing_livehosts.update_one(
        {'id': host['id']},
        {'$set': {'last_login_at': _now()}}
    )
    
    # Create token
    token = _create_livehost_token(host['id'], host['name'], host['email'])
    
    return serialize_doc({
        'token': token,
        'host': {
            'id': host['id'],
            'name': host['name'],
            'email': host['email'],
            'phone': host.get('phone', ''),
            'employment_type': host.get('employment_type', ''),
        }
    })


@router.get('/portal/my-profile')
async def get_my_profile(request: Request):
    """LiveHost views their own profile"""
    host = await require_livehost_auth(request)
    db = get_db()
    
    # Get full profile
    full_host = await db.marketing_livehosts.find_one({'id': host['id']}, {'_id': 0, 'password_hash': 0})
    if not full_host:
        raise HTTPException(404, 'Profile tidak ditemukan')
    
    # Get assigned accounts detail
    if full_host.get('assigned_account_ids'):
        accounts = await db.marketing_platform_accounts.find(
            {'id': {'$in': full_host['assigned_account_ids']}}, {'_id': 0}
        ).to_list(100)
        full_host['assigned_accounts'] = accounts
    else:
        full_host['assigned_accounts'] = []
    
    return serialize_doc(full_host)


@router.get('/portal/my-shifts')
async def get_my_shifts(
    request: Request,
    date_from: Optional[str] = Query(None, description="YYYY-MM-DD"),
    date_to: Optional[str] = Query(None, description="YYYY-MM-DD"),
    status: Optional[str] = Query(None),
):
    """LiveHost views their own shifts"""
    host = await require_livehost_auth(request)
    db = get_db()
    
    # Default to current month if not specified
    if not date_from:
        date_from = _now().strftime('%Y-%m-01')
    if not date_to:
        # Last day of current month
        import calendar
        now = _now()
        last_day = calendar.monthrange(now.year, now.month)[1]
        date_to = now.strftime(f'%Y-%m-{last_day}')
    
    query = {
        'host_id': host['id'],
        'date': {'$gte': date_from, '$lte': date_to}
    }
    if status:
        query['attendance_status'] = status
    
    shifts = await db.marketing_livehost_shifts.find(
        query, {'_id': 0}
    ).sort('date', -1).to_list(500)

    # Normalize field names agar kompatibel dengan LiveHostPortalApp.jsx
    def _norm_shift(s):
        start = s.get('scheduled_start') or s.get('shift_start_time', '')
        end   = s.get('scheduled_end')   or s.get('shift_end_time', '')
        # Hitung durasi jika belum ada
        dur = s.get('scheduled_duration_minutes') or s.get('actual_duration_minutes')
        if not dur and start and end:
            try:
                sh, sm = map(int, start.split(':'))
                eh, em = map(int, end.split(':'))
                dur = max(0, (eh * 60 + em) - (sh * 60 + sm))
            except Exception:
                dur = 0
        return {
            **s,
            'shift_type':               s.get('shift_name') or s.get('shift_type', ''),
            'shift_start_time':         start,
            'shift_end_time':           end,
            'scheduled_duration_minutes': dur or 0,
            'clock_in_time':            s.get('clock_in_time') or s.get('actual_start'),
            'clock_out_time':           s.get('clock_out_time') or s.get('actual_end'),
            'attendance_status':        s.get('attendance_status', 'scheduled'),
        }

    return serialize_doc({
        'shifts': [_norm_shift(s) for s in shifts],
        'date_range': {'from': date_from, 'to': date_to},
        'total': len(shifts),
    })


@router.get('/portal/scripts')
async def get_my_scripts(request: Request):
    """LiveHost views available scripts"""
    host = await require_livehost_auth(request)
    db = get_db()
    
    # Get scripts that are either global or specific to assigned accounts
    query = {
        'is_active': True,
        '$or': [
            {'account_id': None},  # Global scripts
            {'account_id': {'$in': host.get('assigned_account_ids', [])}}  # Account-specific
        ]
    }
    
    scripts = await db.marketing_livehost_scripts.find(
        query, {'_id': 0}
    ).sort('category', 1).to_list(500)
    
    return serialize_doc(scripts)


@router.get('/portal/training')
async def get_my_training(request: Request):
    """LiveHost views their training assignments and progress"""
    host = await require_livehost_auth(request)
    db = get_db()
    
    # Get training progress
    progress_list = await db.marketing_livehost_training_progress.find(
        {'host_id': host['id']}, {'_id': 0}
    ).sort('assigned_at', -1).to_list(500)
    
    # Enrich with training details
    if progress_list:
        training_ids = list(set(p['training_id'] for p in progress_list))
        trainings = await db.marketing_livehost_training.find(
            {'id': {'$in': training_ids}}, {'_id': 0}
        ).to_list(500)
        training_map = {t['id']: t for t in trainings}
        
        for progress in progress_list:
            training = training_map.get(progress['training_id'])
            if training:
                progress['training_detail'] = training
    
    return serialize_doc(progress_list)


@router.post('/portal/training/{progress_id}/complete')
async def portal_complete_training(progress_id: str, request: Request):
    """LiveHost self-marks their training as completed (no admin needed)"""
    host = await require_livehost_auth(request)
    db = get_db()

    progress = await db.marketing_livehost_training_progress.find_one(
        {'id': progress_id, 'host_id': host['id']}, {'_id': 0}
    )
    if not progress:
        raise HTTPException(404, 'Training progress tidak ditemukan atau bukan milik Anda')

    if progress['status'] == 'completed':
        return {'message': 'Training sudah completed', 'already_completed': True}

    training = await db.marketing_livehost_training.find_one(
        {'id': progress['training_id']}, {'_id': 0}
    )
    if not training:
        raise HTTPException(404, 'Training tidak ditemukan')

    # Calculate new expiry date if training has expiry
    expiry_date = None
    if training.get('expiry_months'):
        from dateutil.relativedelta import relativedelta
        expiry_date = _now() + relativedelta(months=training['expiry_months'])

    update_data = {
        'status': 'completed',
        'completed_at': _now(),
        'expiry_date': expiry_date,
        'self_completed': True,
    }

    await db.marketing_livehost_training_progress.update_one(
        {'id': progress_id}, {'$set': update_data}
    )

    # Add to host's training_completed list
    await db.marketing_livehosts.update_one(
        {'id': host['id']},
        {'$addToSet': {'training_completed': progress['training_id']}}
    )

    return {'message': 'Training berhasil di-mark sebagai selesai'}


@router.post('/portal/clock')
async def portal_clock_in_out(data: ClockInOut, request: Request):
    """LiveHost clocks in/out from portal"""
    host = await require_livehost_auth(request)
    db = get_db()
    
    shift = await db.marketing_livehost_shifts.find_one({'id': data.shift_id}, {'_id': 0})
    if not shift:
        raise HTTPException(404, 'Shift tidak ditemukan')
    
    # Verify shift belongs to this host
    if shift['host_id'] != host['id']:
        raise HTTPException(403, 'Shift ini bukan milik Anda')
    
    now = _now()
    
    if data.action == 'clock_in':
        if shift.get('clock_in_time'):
            raise HTTPException(400, 'Shift sudah di-clock in')
        
        # Determine attendance status
        shift_date_str = shift['date']
        shift_start_str = shift['shift_start_time']
        scheduled_datetime_str = f"{shift_date_str}T{shift_start_str}:00+00:00"
        try:
            scheduled_datetime = datetime.fromisoformat(scheduled_datetime_str.replace('+00:00', '')).replace(tzinfo=timezone.utc)
            time_diff = (now - scheduled_datetime).total_seconds() / 60
            if time_diff > 15:
                attendance_status = 'late'
            else:
                attendance_status = 'on_time'
        except Exception:
            attendance_status = 'on_time'
        
        update_data = {
            'clock_in_time': now,
            'attendance_status': attendance_status,
        }
        
        await db.marketing_livehost_shifts.update_one({'id': data.shift_id}, {'$set': update_data})
        
        return serialize_doc({
            'message': f"Clock in berhasil ({attendance_status})",
            'clock_in_time': now,
            'attendance_status': attendance_status,
        })
    
    elif data.action == 'clock_out':
        if not shift.get('clock_in_time'):
            raise HTTPException(400, 'Shift belum di-clock in')
        if shift.get('clock_out_time'):
            raise HTTPException(400, 'Shift sudah di-clock out')
        
        clock_in_time = shift['clock_in_time']
        if clock_in_time.tzinfo is None:
            clock_in_time = clock_in_time.replace(tzinfo=timezone.utc)
        
        actual_duration_minutes = int((now - clock_in_time).total_seconds() / 60)
        
        update_data = {
            'clock_out_time': now,
            'actual_duration_minutes': actual_duration_minutes,
            'attendance_status': 'completed',
        }
        
        await db.marketing_livehost_shifts.update_one({'id': data.shift_id}, {'$set': update_data})
        
        return serialize_doc({
            'message': 'Clock out berhasil',
            'clock_out_time': now,
            'actual_duration_minutes': actual_duration_minutes,
        })
    
    else:
        raise HTTPException(400, 'Action harus clock_in atau clock_out')


# ══════════════════════════════════════════════════════════════════════════════
# WEBSOCKET NOTIFICATIONS (OPTIONAL - Basic Implementation)
# Note: For full WebSocket, use dedicated WebSocket server or Socket.IO
# This is a simple notification endpoint that can be polled
# ══════════════════════════════════════════════════════════════════════════════

@router.get('/portal/notifications')
async def get_my_notifications(request: Request):
    """LiveHost gets their notifications (polling-based fallback for SSE)"""
    host = await require_livehost_auth(request)
    db = get_db()

    # 1. Persisted notifications (from SSOT `notifications` w/ type='marketing_livehost')
    cursor = db.notifications.find(
        {'type': 'marketing_livehost', 'host_id': host['id']},
        {'_id': 0},
    ).sort('created_at', -1).limit(50)
    persisted = [_reshape_lh_notif(d) async for d in cursor]

    # 2. Derived notifications (legacy fallback for backwards compatibility)
    seven_days_ago = (_now() - timedelta(days=7)).strftime('%Y-%m-%d')

    recent_shifts = await db.marketing_livehost_shifts.find({
        'host_id': host['id'],
        'date': {'$gte': seven_days_ago},
        'created_at': {'$gte': _now() - timedelta(days=7)}
    }, {'_id': 0, 'id': 1, 'date': 1, 'shift_type': 1, 'account_name': 1, 'created_at': 1}).sort('created_at', -1).limit(10).to_list(10)

    recent_training = await db.marketing_livehost_training_progress.find({
        'host_id': host['id'],
        'assigned_at': {'$gte': _now() - timedelta(days=7)}
    }, {'_id': 0, 'training_title': 1, 'assigned_at': 1}).sort('assigned_at', -1).limit(10).to_list(10)

    derived = []
    for shift in recent_shifts:
        derived.append({
            'id': f"derived-shift-{shift['id']}",
            'type': 'shift_assigned',
            'title': 'Shift Baru Assigned',
            'message': f"Anda dijadwalkan untuk shift {shift.get('shift_type') or shift.get('shift_name', '')} pada {shift.get('date', '')} di {shift.get('account_name', 'Account')}",
            'created_at': shift['created_at'].isoformat() if hasattr(shift['created_at'], 'isoformat') else str(shift['created_at']),
            'link': f"/shifts/{shift['id']}",
            'read': False,
        })
    for training in recent_training:
        derived.append({
            'id': f"derived-training-{training.get('training_title', 'x')}",
            'type': 'training_assigned',
            'title': 'Training Baru',
            'message': f"Anda di-assign training: {training['training_title']}",
            'created_at': training['assigned_at'].isoformat() if hasattr(training['assigned_at'], 'isoformat') else str(training['assigned_at']),
            'link': '/training',
            'read': False,
        })

    # Merge & sort
    all_notifications = list(persisted) + derived
    all_notifications.sort(key=lambda x: x.get('created_at', ''), reverse=True)

    unread_count = sum(1 for n in all_notifications if not n.get('read'))

    return serialize_doc({
        'notifications': all_notifications[:50],
        'unread_count': unread_count,
    })


# ══════════════════════════════════════════════════════════════════════════════
# LIVEHOST PORTAL — SSE REAL-TIME NOTIFICATIONS
# Pattern consistent with /api/notifications/stream (rahaza_notifications.py)
# `_livehost_sse_subscribers` and `publish_livehost_notification` are now in
# marketing_livehost_shared.py to allow cross-module reuse without circular imports.
# ══════════════════════════════════════════════════════════════════════════════


async def _require_livehost_auth_sse(request: Request) -> dict:
    """
    SSE-compatible auth: accepts Bearer header OR ?token=... query parameter
    (EventSource cannot set custom headers in browsers).
    """
    auth = request.headers.get('Authorization') or request.headers.get('authorization')
    token = None
    if auth and auth.lower().startswith('bearer '):
        token = auth.split(' ', 1)[1].strip()
    if not token:
        token = request.query_params.get('token')
    if not token:
        raise HTTPException(401, 'Tidak ada token')
    payload = _decode_livehost_token(token)
    if not payload:
        raise HTTPException(401, 'Token tidak valid')
    db = get_db()
    host = await db.marketing_livehosts.find_one(
        {'id': payload.get('host_id', payload.get('sub', ''))}, {'_id': 0, 'password_hash': 0}
    )
    if not host:
        raise HTTPException(401, 'LiveHost tidak ditemukan')
    if host.get('status') != 'active':
        raise HTTPException(403, 'LiveHost tidak aktif')
    return host


@router.get('/portal/notifications/stream')
async def livehost_notifications_stream(request: Request):
    """
    Server-Sent Events stream for LiveHost portal.
    Client connects via EventSource('/api/marketing/livehost/portal/notifications/stream?token=<jwt>').
    """
    host = await _require_livehost_auth_sse(request)
    host_id = host['id']
    q: asyncio.Queue = asyncio.Queue()
    _livehost_sse_subscribers[host_id] = q

    async def event_generator():
        try:
            yield f"event: ready\ndata: {json.dumps({'subscribed_at': _now().isoformat(), 'host_id': host_id})}\n\n"
            while True:
                if await request.is_disconnected():
                    break
                try:
                    notif = await asyncio.wait_for(q.get(), timeout=30.0)
                    yield f"event: notification\ndata: {json.dumps(notif, default=str)}\n\n"
                except asyncio.TimeoutError:
                    # heartbeat
                    yield "event: ping\ndata: {}\n\n"
        finally:
            # Cleanup on disconnect
            if _livehost_sse_subscribers.get(host_id) is q:
                _livehost_sse_subscribers.pop(host_id, None)

    return StreamingResponse(
        event_generator(),
        media_type='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no',
            'Connection': 'keep-alive',
        }
    )


@router.post('/portal/notifications/{notif_id}/read')
async def mark_notification_read(notif_id: str, request: Request):
    """LiveHost marks notification as read"""
    host = await require_livehost_auth(request)
    db = get_db()
    result = await db.notifications.update_one(
        {'id': notif_id, 'type': 'marketing_livehost', 'host_id': host['id']},
        {'$set': {'read': True, 'read_at': _now()}}
    )
    if result.matched_count == 0:
        # Allow marking derived notifications as no-op
        return {'message': 'Notification not found or already read', 'read': True}
    return {'message': 'Notification marked as read', 'read': True}


@router.post('/portal/notifications/mark-all-read')
async def mark_all_notifications_read(request: Request):
    """LiveHost marks all their notifications as read"""
    host = await require_livehost_auth(request)
    db = get_db()
    result = await db.notifications.update_many(
        {'type': 'marketing_livehost', 'host_id': host['id'], 'read': False},
        {'$set': {'read': True, 'read_at': _now()}}
    )
    return {'message': 'All notifications marked as read', 'updated': result.modified_count}



# ══════════════════════════════════════════════════════════════════════════════
# DYNAMIC HOST ID ROUTES (MUST be registered LAST to avoid catching
# static segments like /shifts, /scripts, /training, /portal, /payment, /analytics)
# ══════════════════════════════════════════════════════════════════════════════

@router.get('/{host_id}')
async def get_livehost(request: Request, host_id: str = Path(..., regex=UUID_PATH_REGEX)):
    """Admin gets LiveHost detail"""
    await require_auth(request)
    db = get_db()

    host = await db.marketing_livehosts.find_one({'id': host_id}, {'_id': 0, 'password_hash': 0})
    if not host:
        raise HTTPException(404, 'LiveHost tidak ditemukan')

    # Get assigned accounts detail
    if host.get('assigned_account_ids'):
        accounts = await db.marketing_platform_accounts.find(
            {'id': {'$in': host['assigned_account_ids']}}, {'_id': 0}
        ).to_list(500)
        host['assigned_accounts'] = accounts
    else:
        host['assigned_accounts'] = []

    # Get training progress
    progress_list = await db.marketing_livehost_training_progress.find(
        {'host_id': host_id}, {'_id': 0}
    ).to_list(500)
    host['training_progress'] = progress_list

    return serialize_doc(host)


@router.patch('/{host_id}')
async def update_livehost(request: Request, data: LiveHostUpdate, host_id: str = Path(..., regex=UUID_PATH_REGEX)):
    """Admin updates LiveHost"""
    await require_auth(request)
    db = get_db()

    host = await db.marketing_livehosts.find_one({'id': host_id}, {'_id': 0})
    if not host:
        raise HTTPException(404, 'LiveHost tidak ditemukan')

    update_data = {}
    if data.name is not None:
        update_data['name'] = data.name
    if data.email is not None:
        # Check duplicate
        existing = await db.marketing_livehosts.find_one({'email': data.email.lower().strip(), 'id': {'$ne': host_id}})
        if existing:
            raise HTTPException(400, f"Email '{data.email}' sudah digunakan LiveHost lain")
        update_data['email'] = data.email.lower().strip()
    if data.password is not None:
        update_data['password_hash'] = hash_password(data.password)
    if data.phone is not None:
        update_data['phone'] = data.phone
    if data.employment_type is not None:
        update_data['employment_type'] = data.employment_type
    if data.hourly_rate is not None:
        update_data['hourly_rate'] = data.hourly_rate
    if data.shift_preferences is not None:
        update_data['shift_preferences'] = data.shift_preferences
    if data.language_skills is not None:
        update_data['language_skills'] = data.language_skills
    if data.product_expertise is not None:
        update_data['product_expertise'] = data.product_expertise
    if data.assigned_account_ids is not None:
        update_data['assigned_account_ids'] = data.assigned_account_ids
    if data.status is not None:
        update_data['status'] = data.status
    if data.notes is not None:
        update_data['notes'] = data.notes

    update_data['updated_at'] = _now()

    await db.marketing_livehosts.update_one({'id': host_id}, {'$set': update_data})

    user = _get_user(request)
    await log_activity(
        user.get('id', 'system'),
        user.get('name') or user.get('email', 'system'),
        'update', 'marketing_livehost',
        f"Updated LiveHost: {host['name']}"
    )

    updated_host = await db.marketing_livehosts.find_one({'id': host_id}, {'_id': 0, 'password_hash': 0})
    return serialize_doc({'message': 'LiveHost berhasil diupdate', 'host': updated_host})


@router.delete('/{host_id}')
async def delete_livehost(request: Request, host_id: str = Path(..., regex=UUID_PATH_REGEX)):
    """Admin deletes LiveHost (soft delete - set status inactive)"""
    await require_auth(request)
    db = get_db()

    host = await db.marketing_livehosts.find_one({'id': host_id}, {'_id': 0})
    if not host:
        raise HTTPException(404, 'LiveHost tidak ditemukan')

    await db.marketing_livehosts.update_one(
        {'id': host_id},
        {'$set': {'status': 'inactive', 'updated_at': _now()}}
    )

    user = _get_user(request)
    await log_activity(
        user.get('id', 'system'),
        user.get('name') or user.get('email', 'system'),
        'delete', 'marketing_livehost',
        f"Deleted LiveHost: {host['name']}"
    )

    return serialize_doc({'message': 'LiveHost berhasil dihapus (status = inactive)'})
