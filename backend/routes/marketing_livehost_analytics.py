# ruff: noqa: F401
"""
marketing_livehost_analytics.py — Analytics, Payment & Reports
Extracted from marketing_livehost.py (2278 LOC monolith)

Refactored: Session #11.19 Phase 3.2 Batch #2
Endpoints: GET /analytics/host-performance, GET /analytics/shift-analysis, POST /payment/calculate, POST /payment/sync-to-finance, GET /payment/status, GET /sop/download
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
    publish_livehost_notification,
)
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, List
import json
import asyncio

_log = logging.getLogger(__name__)

router = APIRouter(prefix='/api/marketing/livehost', tags=['Marketing-LiveHost-Analytics'])


def _month_bounds(month: Optional[str]) -> tuple:
    """Validasi periode 'YYYY-MM' → ('YYYY', 'MM', date_from, date_to).

    BUG-R11-A (FASE 11) — sebelumnya `month.split('-')` + `int(...)` dijalankan
    tanpa penjagaan, sehingga `?month=99` (atau teks apa pun) melempar
    ValueError yang tidak tertangkap → HTTP 500. Sekarang input yang salah
    dibalas **HTTP 400** dengan pesan jelas, dan bulan kosong tetap
    jatuh ke bulan berjalan seperti perilaku semula.
    """
    if not month or not str(month).strip():
        month = _now().strftime('%Y-%m')
    parts = str(month).strip().split('-')
    if len(parts) < 2:
        raise HTTPException(400, f"Parameter 'month' harus berformat 'YYYY-MM'. Diterima: '{month}'.")
    try:
        y_i, m_i = int(parts[0]), int(parts[1])
    except (TypeError, ValueError):
        raise HTTPException(400, f"Parameter 'month' harus berformat 'YYYY-MM'. Diterima: '{month}'.")
    if not (1970 <= y_i <= 2999):
        raise HTTPException(400, f"Tahun pada 'month' di luar jangkauan (1970–2999). Diterima: '{month}'.")
    if not (1 <= m_i <= 12):
        raise HTTPException(400, f"Bulan pada 'month' harus 1–12. Diterima: '{month}'.")
    year, mon = f"{y_i:04d}", f"{m_i:02d}"
    import calendar
    last_day = calendar.monthrange(y_i, m_i)[1]
    return year, mon, f"{year}-{mon}-01", f"{year}-{mon}-{last_day:02d}"


@router.get('/analytics/host-performance')
async def get_host_performance(
    request: Request,
    month: Optional[str] = Query(None, description="YYYY-MM"),
    host_id: Optional[str] = Query(None),
):
    """Admin views LiveHost performance analytics"""
    await require_auth(request)
    db = get_db()
    
    # Default to current month if not specified
    if not month:
        month = _now().strftime('%Y-%m')
    
    year, mon, date_from, date_to = _month_bounds(month)
    month = f"{year}-{mon}"
    
    # Build query
    query = {
        'date': {'$gte': date_from, '$lte': date_to},
        'attendance_status': 'completed'
    }
    if host_id:
        query['host_id'] = host_id
    
    shifts = await db.marketing_livehost_shifts.find(query, {'_id': 0}).to_list(5000)
    
    # Aggregate by host
    host_stats = {}
    for shift in shifts:
        hid = shift['host_id']
        if hid not in host_stats:
            host_stats[hid] = {
                'host_id': hid,
                'host_name': shift['host_name'],
                'total_shifts': 0,
                'total_hours': 0,
                'total_revenue': 0,
                'total_orders': 0,
                'total_viewers': 0,
                'avg_revenue_per_shift': 0,
                'avg_viewers_per_shift': 0,
                'best_shift_revenue': 0,
                'best_shift_date': None,
            }
        
        stats = host_stats[hid]
        stats['total_shifts'] += 1
        stats['total_hours'] += (shift.get('actual_duration_minutes') or 0) / 60
        stats['total_revenue'] += shift.get('revenue', 0)
        stats['total_orders'] += shift.get('orders', 0)
        stats['total_viewers'] += shift.get('viewers', 0)
        
        # Track best shift
        if shift.get('revenue', 0) > stats['best_shift_revenue']:
            stats['best_shift_revenue'] = shift['revenue']
            stats['best_shift_date'] = shift['date']
    
    # Calculate averages
    for stats in host_stats.values():
        if stats['total_shifts'] > 0:
            stats['avg_revenue_per_shift'] = stats['total_revenue'] / stats['total_shifts']
            stats['avg_viewers_per_shift'] = stats['total_viewers'] / stats['total_shifts']
            stats['avg_orders_per_shift'] = stats['total_orders'] / stats['total_shifts']
    
    # Sort by total revenue descending
    performance_list = sorted(host_stats.values(), key=lambda x: x['total_revenue'], reverse=True)
    
    return serialize_doc({
        'month': month,
        'date_range': {'from': date_from, 'to': date_to},
        'total_hosts': len(performance_list),
        'performance': performance_list,
    })


@router.get('/analytics/shift-analysis')
async def get_shift_analysis(
    request: Request,
    month: Optional[str] = Query(None, description="YYYY-MM"),
):
    """Admin views shift time analysis (best performing shift times)"""
    await require_auth(request)
    db = get_db()
    
    # Default to current month
    if not month:
        month = _now().strftime('%Y-%m')
    
    year, mon, date_from, date_to = _month_bounds(month)
    month = f"{year}-{mon}"
    
    shifts = await db.marketing_livehost_shifts.find({
        'date': {'$gte': date_from, '$lte': date_to},
        'attendance_status': 'completed',
        'revenue': {'$gt': 0}
    }, {'_id': 0}).to_list(5000)
    
    # Analyze by shift type
    shift_type_stats = {}
    for shift in shifts:
        stype = shift.get('shift_type', 'unknown')
        if stype not in shift_type_stats:
            shift_type_stats[stype] = {
                'shift_type': stype,
                'count': 0,
                'total_revenue': 0,
                'total_viewers': 0,
                'avg_revenue': 0,
                'avg_viewers': 0,
            }
        
        stats = shift_type_stats[stype]
        stats['count'] += 1
        stats['total_revenue'] += shift.get('revenue', 0)
        stats['total_viewers'] += shift.get('viewers', 0)
    
    # Calculate averages
    for stats in shift_type_stats.values():
        if stats['count'] > 0:
            stats['avg_revenue'] = stats['total_revenue'] / stats['count']
            stats['avg_viewers'] = stats['total_viewers'] / stats['count']
    
    # Analyze by day of week
    day_stats = {}
    for shift in shifts:
        try:
            date_obj = datetime.fromisoformat(shift['date'])
            day_name = date_obj.strftime('%A')
            
            if day_name not in day_stats:
                day_stats[day_name] = {
                    'day': day_name,
                    'count': 0,
                    'total_revenue': 0,
                    'avg_revenue': 0,
                }
            
            day_stats[day_name]['count'] += 1
            day_stats[day_name]['total_revenue'] += shift.get('revenue', 0)
        except Exception:
            logging.getLogger(__name__).debug("suppressed exception", exc_info=True)
    
    # Calculate averages for days
    for stats in day_stats.values():
        if stats['count'] > 0:
            stats['avg_revenue'] = stats['total_revenue'] / stats['count']
    
    # Sort
    shift_type_list = sorted(shift_type_stats.values(), key=lambda x: x['avg_revenue'], reverse=True)
    day_list = sorted(day_stats.values(), key=lambda x: x['avg_revenue'], reverse=True)
    
    return serialize_doc({
        'month': month,
        'by_shift_type': shift_type_list,
        'by_day_of_week': day_list,
    })


# ══════════════════════════════════════════════════════════════════════════════
# PAYMENT CALCULATION & SYNC TO FINANCE
# ══════════════════════════════════════════════════════════════════════════════

@router.post('/payment/calculate')
async def calculate_payments(
    request: Request,
    month: str = Query(..., description="YYYY-MM"),
):
    """SESI #34 — **UPAH PER-SESI DIHAPUS. Host live digaji BULANAN.**

    Keputusan pemilik (2026-08-23): "livehost digaji bulanan bukan persesi jadi
    untuk sesi livehost itu dihapus saja" + "harus tersambung ke payroll HR".

    Yang berubah, dan kenapa:
    * Perhitungan lama (jam × `hourly_rate` + bonus 10% omzet − denda telat)
      MENGARANG angka gaji di luar payroll: hasilnya masuk `total_pay` shift dan
      ikut terbaca sebagai biaya marketing, padahal HR membayar gaji bulanan.
      Satu orang dibayar dua kali di dua buku.
    * Sekarang endpoint ini TIDAK menghitung upah. Ia hanya MENANDAI shift bulan
      itu sebagai `pay_mode='monthly_salary'` (upah per-sesi = 0) dan melaporkan
      gaji bulanan host dari **master HR** (`rahaza_employees`) lewat
      `livehost.employee_id`. Log aktivitas live (jam tayang, omzet, penonton)
      TETAP DISIMPAN — pemilik memintanya untuk KPI.
    * Host yang belum ditautkan ke karyawan HR DILAPORKAN sebagai kekurangan
      (`unlinked`), bukan diberi angka 0 diam-diam.
    """
    await require_auth(request)
    db = get_db()

    year, mon, date_from, date_to = _month_bounds(month)
    month = f"{year}-{mon}"

    shifts = await db.marketing_livehost_shifts.find({
        'date': {'$gte': date_from, '$lte': date_to},
    }, {'_id': 0}).to_list(10000)

    host_ids = sorted({s['host_id'] for s in shifts if s.get('host_id')})
    hosts = await db.marketing_livehosts.find(
        {'id': {'$in': host_ids}},
        {'_id': 0, 'id': 1, 'name': 1, 'employee_id': 1, 'monthly_salary': 1}
    ).to_list(500)
    from core import livehost_salary as _lhs
    sal = await _lhs.monthly_salary_map(db, hosts)

    # Upah per-sesi DINOLKAN (sekali, idempoten) — angka lama tidak boleh terus
    # terbaca sebagai biaya. Nilainya sebelum dinolkan disimpan di `legacy_pay`
    # supaya jejaknya tidak hilang.
    zeroed = 0
    for sh in shifts:
        if sh.get('pay_mode') == 'monthly_salary':
            continue
        legacy = {k: sh.get(k, 0) for k in ('base_pay', 'bonus', 'penalty', 'total_pay')}
        await db.marketing_livehost_shifts.update_one({'id': sh['id']}, {'$set': {
            'pay_mode': 'monthly_salary',
            'base_pay': 0, 'bonus': 0, 'penalty': 0, 'total_pay': 0,
            'payment_status': 'monthly_salary',
            'legacy_pay': legacy,
            'pay_note': 'Host digaji bulanan lewat payroll HR — tidak dibayar per sesi.',
            'calculated_at': _now(),
            'calculated_by': _get_user(request).get('email', 'system'),
        }})
        zeroed += 1

    rows, unlinked, total_salary = [], [], 0.0
    for h in hosts:
        info = sal.get(h['id']) or {'salary': 0.0, 'source': 'none', 'reason': ''}
        salary = float(info.get('salary') or 0)
        n_shifts = sum(1 for s in shifts if s.get('host_id') == h['id'])
        hours = round(sum((s.get('actual_duration_minutes') or 0) for s in shifts
                          if s.get('host_id') == h['id']) / 60, 1)
        if salary <= 0:
            unlinked.append({'host_id': h['id'], 'host_name': h.get('name'),
                             'reason': info.get('reason') or 'gaji bulanan belum ada di payroll HR'})
        else:
            total_salary += salary
        rows.append({
            'host_id': h['id'], 'host_name': h.get('name'),
            'employee_id': info.get('employee_id') or '',
            'employee_name': info.get('employee_name') or '',
            'monthly_salary_hr': salary,
            'salary_source': info.get('source'),
            'salary_gap': info.get('reason') or '',
            'shifts': n_shifts, 'hours_live': hours,
        })

    user = _get_user(request)
    await log_activity(
        user.get('id', 'system'), user.get('name') or user.get('email', 'system'),
        'update', 'marketing_livehost_payment_calculation',
        f"Livehost {month}: upah per-sesi dinolkan ({zeroed} shift) — gaji bulanan dari payroll HR")

    return serialize_doc({
        'message': (f"Host live digaji BULANAN lewat payroll HR. {zeroed} shift bulan {month} "
                    f"dibersihkan dari upah per-sesi. "
                    + (f"{len(unlinked)} host belum ditautkan ke karyawan HR."
                       if unlinked else "Semua host sudah tertaut ke karyawan HR.")),
        'pay_mode': 'monthly_salary',
        'month': month,
        'shifts_normalized': zeroed,
        'hosts': rows,
        'unlinked_hosts': unlinked,
        'monthly_salary_total': round(total_salary, 2),
        'calculated': 0,
    })


@router.post('/payment/sync-to-finance')
async def sync_payments_to_finance(
    request: Request,
    month: str = Query(..., description="YYYY-MM"),
):
    """Admin syncs calculated payments to Finance/Payroll module"""
    await require_auth(request)
    db = get_db()
    
    year, mon, date_from, date_to = _month_bounds(month)
    month = f"{year}-{mon}"
    
    # Get all calculated shifts that haven't been synced
    shifts = await db.marketing_livehost_shifts.find({
        'date': {'$gte': date_from, '$lte': date_to},
        'payment_status': 'calculated'
    }, {'_id': 0}).to_list(5000)
    
    if not shifts:
        return serialize_doc({'message': 'Tidak ada payment yang perlu di-sync', 'synced': 0})
    
    # Aggregate by host
    host_payments = {}
    for shift in shifts:
        host_id = shift['host_id']
        if host_id not in host_payments:
            host_payments[host_id] = {
                'host_id': host_id,
                'host_name': shift['host_name'],
                'shifts': [],
                'total_base_pay': 0,
                'total_bonus': 0,
                'total_penalty': 0,
                'total_payment': 0,
            }
        
        hp = host_payments[host_id]
        hp['shifts'].append({
            'shift_id': shift['id'],
            'date': shift['date'],
            'base_pay': shift.get('base_pay', 0),
            'bonus': shift.get('bonus', 0),
            'penalty': shift.get('penalty', 0),
            'total': shift.get('total_pay', 0),
        })
        hp['total_base_pay'] += shift.get('base_pay', 0)
        hp['total_bonus'] += shift.get('bonus', 0)
        hp['total_penalty'] += shift.get('penalty', 0)
        hp['total_payment'] += shift.get('total_pay', 0)
    
    # RC-12 (keputusan produk 1a): write ke `payroll_entries` DIHAPUS — koleksi hantu
    # (0 reader; payroll nyata = rahaza_payslips/rahaza_payroll_runs, tak pernah membacanya).
    # Komisi/pembayaran host tetap dihitung & tampil di Livehost Analytics (rekap di bawah);
    # state machine shift (pending→calculated→synced_to_finance) dipertahankan.
    synced_count = 0
    for host_id, payment_data in host_payments.items():
        synced_count += 1

        # SSE: notify host rekap pembayarannya sudah difinalkan
        try:
            await publish_livehost_notification(
                db,
                host_id=host_id,
                type_='payment_synced',
                severity='success',
                title='Rekap Pembayaran Difinalkan',
                message=f"Rekap pembayaran bulan {month} (Rp {payment_data['total_payment']:,.0f}) telah difinalkan dan tercatat di Livehost Analytics",
                link='/payments',
            )
        except Exception:
            logging.getLogger(__name__).debug("suppressed exception", exc_info=True)
    
    # Mark shifts as synced
    shift_ids = [s['id'] for s in shifts]
    await db.marketing_livehost_shifts.update_many(
        {'id': {'$in': shift_ids}},
        {'$set': {
            'payment_status': 'synced_to_finance',
            'synced_at': _now(),
            'synced_by': _get_user(request).get('email', 'system'),
        }}
    )
    
    user = _get_user(request)
    await log_activity(
        user.get('id', 'system'),
        user.get('name') or user.get('email', 'system'),
        'create', 'marketing_livehost_payment_sync',
        f"Synced payment for {synced_count} LiveHosts ({len(shifts)} shifts) in {month} to Finance"
    )
    
    return serialize_doc({
        'message': f'Payment berhasil di-sync ke Finance untuk {synced_count} LiveHost',
        'synced_hosts': synced_count,
        'synced_shifts': len(shifts),
        'month': month,
    })


@router.get('/payment/status')
async def get_payment_status(
    request: Request,
    month: str = Query(..., description="YYYY-MM"),
):
    """Admin views payment status summary for a month"""
    await require_auth(request)
    db = get_db()
    
    year, mon, date_from, date_to = _month_bounds(month)
    month = f"{year}-{mon}"
    
    # Aggregate shifts by payment status
    pipeline = [
        {'$match': {
            'date': {'$gte': date_from, '$lte': date_to},
            'attendance_status': 'completed'
        }},
        {'$group': {
            '_id': '$payment_status',
            'count': {'$sum': 1},
            'total_pay': {'$sum': '$total_pay'}
        }}
    ]
    
    results = await db.marketing_livehost_shifts.aggregate(pipeline).to_list(100)
    
    status_summary = {
        'pending': {'count': 0, 'total_pay': 0},
        'calculated': {'count': 0, 'total_pay': 0},
        'synced_to_finance': {'count': 0, 'total_pay': 0},
    }
    
    for result in results:
        status = result['_id'] or 'pending'
        if status in status_summary:
            status_summary[status] = {
                'count': result['count'],
                'total_pay': result['total_pay']
            }
    
    return serialize_doc({
        'month': month,
        'status_summary': status_summary,
        'total_completed_shifts': sum(s['count'] for s in status_summary.values()),
        'total_amount': sum(s['total_pay'] for s in status_summary.values()),
    })


# ══════════════════════════════════════════════════════════════════════════════
# SOP DOCUMENT (PDF) — ADMIN ONLY
# ══════════════════════════════════════════════════════════════════════════════

@router.get('/sop/download')
async def download_livehost_sop(request: Request):
    """
    Download the LiveHost Management SOP as a PDF document.
    Accessible to authenticated admin users.
    """
    await require_auth(request)
    from fastapi.responses import Response
    from utils.livehost_sop_pdf import build_livehost_sop_pdf

    pdf_bytes = build_livehost_sop_pdf(company_name='CV. DEWI ADITYA OFFICIAL')
    filename = f'SOP_LiveHost_v1.0_{_now().strftime("%Y%m%d")}.pdf'
    return Response(
        content=pdf_bytes,
        media_type='application/pdf',
        headers={
            'Content-Disposition': f'attachment; filename="{filename}"',
        }
    )


# ══════════════════════════════════════════════════════════════════════════════
# PHASE 4: LIVEHOST PORTAL (Separate Portal for LiveHost)
