# ruff: noqa: F401
"""
marketing_livehost_shifts.py — Shift Scheduling & Clock Management
Extracted from marketing_livehost.py (2278 LOC monolith)

Refactored: Session #11.19 Phase 3.2 Batch #2
Endpoints: POST /shifts, GET /shifts, GET /shifts/calendar, PATCH /shifts/{id}, DELETE /shifts/{id}, POST /clock, POST /shifts/{id}/performance
"""
from fastapi import APIRouter, HTTPException, Request, Query, Path
from fastapi.responses import StreamingResponse
# F6 (sesi #10) — endpoint DAFTAR/RINGKAS wajib menyaring sendiri: jaring
# pengaman middleware hanya menolak permintaan yang MENYEBUT toko, ia tidak
# tahu isi jawaban. Tanpa ini staf pemegang satu toko membaca angka 9 toko.
from core import marketing_account_scope as _scope
from database import get_db
from auth import require_auth, serialize_doc, log_activity
from routes.marketing_livehost_shared import (
    _uid, _now, _get_user, _create_livehost_token, _decode_livehost_token,
    require_livehost_auth, LiveHostCreate, LiveHostUpdate, ShiftCreate, ShiftUpdate,
    ClockInOut, ShiftPerformanceRecord, ScriptCreate, TrainingCreate, TrainingAssign,
    TrainingComplete, LiveHostLoginIn, UPLOAD_DIR, UUID_PATH_REGEX,
    _notif_insert_ssot, _reshape_lh_notif,
    publish_livehost_notification,
)
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, List
import json
import asyncio

_log = logging.getLogger(__name__)

router = APIRouter(prefix='/api/marketing/livehost', tags=['Marketing-LiveHost-Shifts'])

@router.post('/shifts')
async def create_shift(data: ShiftCreate, request: Request):
    """Admin creates a shift assignment"""
    await require_auth(request)
    db = get_db()
    
    # Validate host
    host = await db.marketing_livehosts.find_one({'id': data.host_id}, {'_id': 0})
    if not host:
        raise HTTPException(404, 'LiveHost tidak ditemukan')
    if host.get('status') != 'active':
        raise HTTPException(400, 'LiveHost tidak aktif')
    
    # Validate account
    account = await db.marketing_platform_accounts.find_one({'id': data.account_id}, {'_id': 0})
    if not account:
        raise HTTPException(404, 'Platform account tidak ditemukan')
    
    # Check shift conflict (same host, same date, overlapping time)
    existing_shifts = await db.marketing_livehost_shifts.find({
        'host_id': data.host_id,
        'date': data.date,
    }, {'_id': 0}).to_list(100)
    
    for existing in existing_shifts:
        # Simple time overlap check
        if (data.shift_start_time < existing['shift_end_time'] and 
            data.shift_end_time > existing['shift_start_time']):
            raise HTTPException(
                400, 
                f"Conflict: Host sudah ada shift pada {data.date} ({existing['shift_start_time']}-{existing['shift_end_time']})"
            )
    
    # Calculate scheduled duration
    try:
        start_h, start_m = map(int, data.shift_start_time.split(':'))
        end_h, end_m = map(int, data.shift_end_time.split(':'))
        scheduled_duration_minutes = (end_h * 60 + end_m) - (start_h * 60 + start_m)
        if scheduled_duration_minutes <= 0:
            scheduled_duration_minutes += 24 * 60  # Next day
    except Exception:
        raise HTTPException(400, 'Format waktu tidak valid (gunakan HH:MM)')
    
    shift = {
        'id': _uid(),
        'host_id': data.host_id,
        'host_name': host['name'],
        'account_id': data.account_id,
        'account_name': account['account_name'],
        'date': data.date,
        'shift_type': data.shift_type,
        'shift_start_time': data.shift_start_time,
        'shift_end_time': data.shift_end_time,
        'scheduled_duration_minutes': scheduled_duration_minutes,
        
        # Attendance (will be filled during clock in/out)
        'clock_in_time': None,
        'clock_out_time': None,
        'actual_duration_minutes': None,
        'attendance_status': 'scheduled',  # scheduled | on_time | late | no_show | completed
        
        # Performance (will be filled after shift)
        'platform': None,
        'viewers': 0,
        'peak_viewers': 0,
        'revenue': 0,
        'orders': 0,
        'items_promoted': [],
        
        # Script & Training
        'script_ids_used': [],
        'script_adherence_score': None,
        
        # Notes
        'notes': data.notes or '',
        'challenges_faced': '',
        'screenshot_url': None,
        
        # Payment (will be calculated after completion)
        'base_pay': 0,
        'bonus': 0,
        'penalty': 0,
        'total_pay': 0,
        'payment_status': 'pending',  # pending | calculated | synced_to_finance
        
        'created_at': _now(),
        'created_by': _get_user(request).get('email', 'system'),
        'reviewed_by': None,
        'reviewed_at': None,
    }
    
    await db.marketing_livehost_shifts.insert_one(shift)
    
    user = _get_user(request)
    await log_activity(
        user.get('id', 'system'),
        user.get('name') or user.get('email', 'system'),
        'create', 'marketing_livehost_shift',
        f"Created shift for {host['name']} on {data.date} ({data.shift_start_time}-{data.shift_end_time})"
    )

    # SSE: notify host about new shift assignment
    try:
        await publish_livehost_notification(
            db,
            host_id=data.host_id,
            type_='shift_assigned',
            severity='info',
            title='Shift Baru Assigned',
            message=f"Shift {data.shift_type} pada {data.date} ({data.shift_start_time}-{data.shift_end_time}) di {account['account_name']}",
            link=f"/shifts/{shift['id']}",
        )
    except Exception:
        logging.getLogger(__name__).debug("suppressed exception", exc_info=True)

    return serialize_doc({'message': 'Shift berhasil dibuat', 'shift': shift})


@router.get('/shifts')
async def list_shifts(
    request: Request,
    host_id: Optional[str] = Query(None),
    account_id: Optional[str] = Query(None),
    date_from: Optional[str] = Query(None, description="YYYY-MM-DD"),
    date_to: Optional[str] = Query(None, description="YYYY-MM-DD"),
    attendance_status: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
):
    """Admin lists shifts with filters and pagination"""
    user = await require_auth(request)
    db = get_db()

    # F6 (sesi #10) — jadwal shift host menempel pada toko.
    query = await _scope.scope_filter(db, user, {})
    if host_id:
        query['host_id'] = host_id
    if account_id:
        query['account_id'] = account_id
    if date_from or date_to:
        query['date'] = {}
        if date_from:
            query['date']['$gte'] = date_from
        if date_to:
            query['date']['$lte'] = date_to
    if attendance_status:
        query['attendance_status'] = attendance_status
    
    total = await db.marketing_livehost_shifts.count_documents(query)
    skip = (page - 1) * limit
    
    shifts = await db.marketing_livehost_shifts.find(
        query, {'_id': 0}
    ).sort('date', -1).skip(skip).limit(limit).to_list(500)
    
    return serialize_doc({
        'shifts': shifts,
        'pagination': {
            'total': total,
            'page': page,
            'limit': limit,
            'total_pages': (total + limit - 1) // limit if total > 0 else 1,
            'has_next': skip + limit < total,
            'has_prev': page > 1,
        }
    })


@router.get('/shifts/calendar')
async def get_shifts_calendar(
    request: Request,
    date_from: str = Query(..., description="YYYY-MM-DD"),
    date_to: str = Query(..., description="YYYY-MM-DD"),
    host_id: Optional[str] = Query(None),
):
    """Get shifts for calendar view (weekly/monthly)"""
    user = await require_auth(request)
    db = get_db()

    query = await _scope.scope_filter(
        db, user, {'date': {'$gte': date_from, '$lte': date_to}})
    if host_id:
        query['host_id'] = host_id
    
    shifts = await db.marketing_livehost_shifts.find(
        query, {'_id': 0}
    ).sort('date', 1).to_list(500)
    
    # Group by date for easy rendering
    calendar = {}
    for shift in shifts:
        date = shift['date']
        if date not in calendar:
            calendar[date] = []
        calendar[date].append(shift)
    
    return serialize_doc({
        'date_from': date_from,
        'date_to': date_to,
        'calendar': calendar,
        'total_shifts': len(shifts),
    })


@router.patch('/shifts/{shift_id}')
async def update_shift(shift_id: str, data: ShiftUpdate, request: Request):
    """Admin updates shift details"""
    await require_auth(request)
    db = get_db()
    
    shift = await db.marketing_livehost_shifts.find_one({'id': shift_id}, {'_id': 0})
    if not shift:
        raise HTTPException(404, 'Shift tidak ditemukan')
    
    update_data = {}
    if data.host_id is not None:
        host = await db.marketing_livehosts.find_one({'id': data.host_id}, {'_id': 0})
        if not host:
            raise HTTPException(404, 'LiveHost tidak ditemukan')
        update_data['host_id'] = data.host_id
        update_data['host_name'] = host['name']
    if data.account_id is not None:
        account = await db.marketing_platform_accounts.find_one({'id': data.account_id}, {'_id': 0})
        if not account:
            raise HTTPException(404, 'Platform account tidak ditemukan')
        update_data['account_id'] = data.account_id
        update_data['account_name'] = account['account_name']
    if data.date is not None:
        update_data['date'] = data.date
    if data.shift_type is not None:
        update_data['shift_type'] = data.shift_type
    if data.shift_start_time is not None:
        update_data['shift_start_time'] = data.shift_start_time
    if data.shift_end_time is not None:
        update_data['shift_end_time'] = data.shift_end_time
    if data.notes is not None:
        update_data['notes'] = data.notes
    
    # Recalculate duration if time changed
    if data.shift_start_time or data.shift_end_time:
        start_time = data.shift_start_time or shift['shift_start_time']
        end_time = data.shift_end_time or shift['shift_end_time']
        try:
            start_h, start_m = map(int, start_time.split(':'))
            end_h, end_m = map(int, end_time.split(':'))
            scheduled_duration_minutes = (end_h * 60 + end_m) - (start_h * 60 + start_m)
            if scheduled_duration_minutes <= 0:
                scheduled_duration_minutes += 24 * 60
            update_data['scheduled_duration_minutes'] = scheduled_duration_minutes
        except Exception:
            logging.getLogger(__name__).debug("suppressed exception", exc_info=True)
    
    update_data['updated_at'] = _now()
    
    await db.marketing_livehost_shifts.update_one({'id': shift_id}, {'$set': update_data})
    
    return serialize_doc({'message': 'Shift berhasil diupdate'})


@router.delete('/shifts/{shift_id}')
async def delete_shift(shift_id: str, request: Request):
    """Admin deletes shift"""
    await require_auth(request)
    db = get_db()
    
    shift = await db.marketing_livehost_shifts.find_one({'id': shift_id}, {'_id': 0})
    if not shift:
        raise HTTPException(404, 'Shift tidak ditemukan')
    
    # Only allow delete if not yet clocked in
    if shift.get('clock_in_time'):
        raise HTTPException(400, 'Tidak dapat menghapus shift yang sudah dimulai. Gunakan update status.')
    
    await db.marketing_livehost_shifts.delete_one({'id': shift_id})
    
    return serialize_doc({'message': 'Shift berhasil dihapus'})


# ══════════════════════════════════════════════════════════════════════════════
# CLOCK IN/OUT
# ══════════════════════════════════════════════════════════════════════════════

@router.post('/clock')
async def clock_in_out(data: ClockInOut, request: Request):
    """LiveHost or Admin clock in/out for a shift (simple timestamp)"""
    # Can be called by admin OR livehost portal
    try:
        await require_auth(request)
    except Exception:
        await require_livehost_auth(request)
    
    db = get_db()
    shift = await db.marketing_livehost_shifts.find_one({'id': data.shift_id}, {'_id': 0})
    if not shift:
        raise HTTPException(404, 'Shift tidak ditemukan')
    
    now = _now()
    
    if data.action == 'clock_in':
        if shift.get('clock_in_time'):
            raise HTTPException(400, 'Shift sudah di-clock in')
        
        # Determine attendance status (on_time or late)
        # Simple check: if clock_in > 15 minutes after shift_start_time, mark as late
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
        # Ensure clock_in_time is timezone-aware
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
# SHIFT PERFORMANCE RECORDING
# ══════════════════════════════════════════════════════════════════════════════

@router.post('/shifts/{shift_id}/performance')
async def record_shift_performance(shift_id: str, data: ShiftPerformanceRecord, request: Request):
    """Admin or LiveHost records performance for a completed shift"""
    # Can be called by admin OR livehost portal
    try:
        await require_auth(request)
        caller_email = _get_user(request).get('email', 'admin')
    except Exception:
        host = await require_livehost_auth(request)
        caller_email = host['email']
    
    db = get_db()
    
    if data.shift_id != shift_id:
        raise HTTPException(400, 'Shift ID tidak cocok')
    
    shift = await db.marketing_livehost_shifts.find_one({'id': shift_id}, {'_id': 0})
    if not shift:
        raise HTTPException(404, 'Shift tidak ditemukan')
    
    if not shift.get('clock_out_time'):
        raise HTTPException(400, 'Shift belum di-clock out. Selesaikan shift terlebih dahulu.')
    
    update_data = {
        'platform': data.platform,
        'viewers': data.viewers,
        'peak_viewers': data.peak_viewers,
        'revenue': data.revenue,
        'orders': data.orders,
        'items_promoted': data.items_promoted or [],
        'script_ids_used': data.script_ids_used or [],
        'script_adherence_score': data.script_adherence_score,
        'challenges_faced': data.challenges_faced or '',
        'notes': shift.get('notes', '') + '\n' + (data.notes or ''),
        'reviewed_by': caller_email,
        'reviewed_at': _now(),
    }
    
    await db.marketing_livehost_shifts.update_one({'id': shift_id}, {'$set': update_data})

    # Sinkronkan ke Sales Marketing (revenue_type='live') agar tidak "slip".
    try:
        from routes.marketing_live_sales_sync import sync_live_sales_to_marketing
        await sync_live_sales_to_marketing(db, shift.get('account_id'), shift.get('date'))
    except Exception:
        logging.getLogger(__name__).warning("sync_live_sales_to_marketing gagal (shift)", exc_info=True)

    return serialize_doc({'message': 'Performance shift berhasil dicatat'})


# ══════════════════════════════════════════════════════════════════════════════
# PHASE 2: SCRIPT LIBRARY & TRAINING MANAGEMENT
