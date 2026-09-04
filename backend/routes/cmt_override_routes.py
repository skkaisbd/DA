"""routes/cmt_override_routes.py — API pendukung **Portal CMT Override**.

Endpoint di sini BUKAN mirror modul vendor (11 modul itu memakai endpoint aslinya
lewat header ``X-CMT-Override-Vendor`` — lihat ``core/cmt_override.py``). Yang ada
di sini hanya tiga hal yang TIDAK punya padanan di portal vendor:

1. ``GET /api/cmt-override/vendors``  — daftar vendor yang boleh diwakili, plus
   data untuk **peringatan dobel input** (keputusan owner 5a) dan ringkasan
   pekerjaan tertunda supaya staf tahu vendor mana yang perlu diisi.
2. ``GET /api/cmt-override/context``  — validasi + info vendor yang sedang
   diwakili (dipakai banner "Anda mengisi ATAS NAMA …").
3. ``GET /api/cmt-override/audit``    — panel transparansi: dokumen mana yang
   diinput STAF vs diisi VENDOR sendiri (keputusan owner 3a).
4. ``GET /api/cmt-override/daily-recap``        — **Rekap Harian** (2026-08-08):
   satu layar "vendor mana yang belum diisi hari ini", checklist per tugas.
5. ``POST /api/cmt-override/daily-recap/remind`` — tegur vendor yang belum diisi
   (idempoten per vendor per tanggal — tombol diklik dua kali tidak menggandakan).
6. ``GET /api/cmt-override/daily-recap/export``  — rekap yang sama dalam Excel/PDF.
7. ``GET /api/cmt-override/weekly-recap``        — **Rekap Mingguan** (2026-08-10):
   7 hari BERGULIR yang berakhir di ``?date=``; meringkas `build_recap()` per hari
   (bukan perhitungan kedua) ⇒ tab Mingguan mustahil berbeda dari tab Harian.
8. ``GET /api/cmt-override/weekly-recap/export`` — rekap mingguan dalam Excel/PDF.

Kebijakan akses: hanya role di ``core.cmt_override.OVERRIDE_ROLES``.
"""
import io
import logging

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse

from auth import log_activity, require_auth, serialize_doc
from database import get_db
from core.cmt_override import (OVERRIDE_HEADER, OVERRIDE_ROLES, is_override_role,
                               resolve_override)
from core.cmt_daily_recap import (MAX_WEEK_DAYS, RECAP_REMINDER_TYPE, WEEK_DAYS,
                                  build_recap, build_week, build_week_comparison,
                                  parse_day, pending_vendor_rows,
                                  send_recap_reminders, vendor_account_info)
from routes.shared import new_id, now

_log = logging.getLogger(__name__)

router = APIRouter(prefix='/api/cmt-override', tags=['cmt-override'])


def _guard(user: dict):
    """Hanya staf DA berhak. Akun vendor ditolak (tidak boleh menyamar)."""
    from routes.production_rbac import is_vendor
    if is_vendor(user):
        raise HTTPException(403, 'Akun vendor tidak boleh membuka Portal CMT Override.')
    if not is_override_role(user):
        raise HTTPException(
            403,
            'Anda tidak berhak membuka Portal CMT Override. '
            f"Role yang diizinkan: {', '.join(sorted(OVERRIDE_ROLES))}.")


# ── Koleksi yang membawa stempel override (SSOT satu tempat) ────────────────
# (collection, label, field nomor dokumen, prefiks field stempel)
#
# Prefiks stempel berbeda karena satu dokumen bisa punya DUA peristiwa:
#   * `vendor_shipments` dibuat DA, tetapi **diterima** vendor ⇒ `receipt_*`
#   * `reminders` dibuat DA, tetapi **dibalas** vendor        ⇒ `response_*`
_AUDIT_SOURCES = [
    ('vendor_shipments',            'Penerimaan Material',  'shipment_number', 'receipt_'),
    ('vendor_material_inspections', 'Inspeksi Material',    'shipment_number', ''),
    ('material_requests',           'Permintaan Material',  'request_number',  ''),
    ('production_jobs',             'Pekerjaan Produksi',   'job_number',      ''),
    ('production_progress',         'Progress Produksi',    'sku',             ''),
    ('buyer_shipments',             'Kirim ke Buyer',       'shipment_number', ''),
    ('production_variances',        'Laporan Variance',     'job_number',      ''),
    ('reminders',                   'Inbox Reminder',       'subject',         'response_'),
]


async def _vendor_filter(db, coll: str, vendor_id: str) -> dict:
    """Filter "milik vendor X" per koleksi.

    `production_progress` TIDAK menyimpan `vendor_id` (dokumennya menempel ke
    `job_id`), jadi kalau disaring dengan `vendor_id` hasilnya SELALU kosong dan
    modul Progress Produksi hilang dari panel audit — padahal justru progress
    inilah angka yang menentukan tagihan. Karena itu vendor di-resolusi lewat
    `production_jobs`.
    """
    if not vendor_id:
        return {}
    if coll == 'production_progress':
        job_ids = await db.production_jobs.distinct('id', {'vendor_id': vendor_id})
        return {'$or': [{'job_id': {'$in': job_ids}},
                        {'on_behalf_of_vendor': vendor_id},
                        {'garment_id': vendor_id}]}
    return {'vendor_id': vendor_id}


@router.get('/vendors')
async def list_override_vendors(request: Request):
    """Vendor yang boleh diwakili + data peringatan dobel input.

    Keputusan owner **4a**: tampilkan **SEMUA vendor aktif** di master CMT
    (`vendor_partners`) — tidak ada flag "tidak pakai sistem".
    `?include_inactive=true` untuk ikut menampilkan yang non-aktif (read-only;
    memilihnya tetap ditolak oleh `resolve_override`).
    """
    user = await require_auth(request)
    _guard(user)
    db = get_db()
    include_inactive = (request.query_params.get('include_inactive') or '').lower() == 'true'

    q = {} if include_inactive else {
        '$and': [{'is_active': {'$ne': False}}, {'active': {'$ne': False}}]
    }
    partners = await db.vendor_partners.find(q, {'_id': 0}).sort('name', 1).to_list(500)
    if not partners:
        return {'vendors': [], 'total': 0, 'override_header': OVERRIDE_HEADER}

    pids = [p['id'] for p in partners]

    # ── Akun portal per vendor (untuk peringatan 5a) ─────────────────────────
    # SSOT `core.cmt_daily_recap.vendor_account_info` — dipakai bersama layar
    # Rekap Harian supaya kedua layar tidak pernah beda jawaban soal "punya akun".
    acc_info = await vendor_account_info(db, pids)

    # ── Ringkasan pekerjaan tertunda (supaya staf tahu mana yang perlu diisi) ─
    async def _counts(coll, match_extra):
        rows = await db[coll].aggregate([
            {'$match': {'vendor_id': {'$in': pids}, **match_extra}},
            {'$group': {'_id': '$vendor_id', 'n': {'$sum': 1}}},
        ]).to_list(None)
        return {r['_id']: r['n'] for r in rows}

    incoming_map = await _counts('vendor_shipments', {'status': 'Sent'})
    uninspected_map = await _counts('vendor_shipments',
                                    {'status': 'Received',
                                     'inspection_status': {'$ne': 'Inspected'}})
    active_job_map = await _counts('production_jobs', {'status': 'In Progress'})
    open_reminder_map = await _counts('reminders', {'status': 'pending'})

    out = []
    for p in partners:
        info = acc_info.get(p['id'], {})
        accs = info.get('accounts', [])
        active_accs = info.get('active_accounts', [])
        last_login = info.get('last_login_at')
        has_active = info.get('has_active', False)
        warning = ''
        if has_active:
            warning = (
                'Vendor ini punya akun portal aktif'
                + (f" (terakhir login {serialize_doc(last_login)})" if last_login
                   else ' (belum pernah login)')
                + ' — hati-hati dobel input.'
            )
        pending = (incoming_map.get(p['id'], 0) + uninspected_map.get(p['id'], 0)
                   + open_reminder_map.get(p['id'], 0))
        out.append({
            'id': p['id'],
            'name': p.get('name', ''),
            'code': p.get('code', ''),
            'contact_name': p.get('contact_name', ''),
            'contact_phone': p.get('contact_phone', ''),
            'capacity_pcs': p.get('capacity_pcs', 0),
            'is_active': p.get('is_active') is not False and p.get('active') is not False,
            'account_count': len(accs),
            'active_account_count': len(active_accs),
            'has_active_portal_account': has_active,
            'last_login_at': serialize_doc(last_login),
            'accounts': [{'email': a.get('email', ''), 'name': a.get('name', ''),
                          'is_active': a.get('is_active') is not False,
                          'last_login_at': serialize_doc(a.get('last_login_at'))}
                         for a in accs],
            'warning': warning,
            'incoming_shipments': incoming_map.get(p['id'], 0),
            'uninspected_shipments': uninspected_map.get(p['id'], 0),
            'active_jobs': active_job_map.get(p['id'], 0),
            'open_reminders': open_reminder_map.get(p['id'], 0),
            'pending_actions': pending,
        })
    return {'vendors': out, 'total': len(out), 'override_header': OVERRIDE_HEADER}


@router.get('/context')
async def override_context(request: Request):
    """Info vendor yang sedang diwakili (untuk banner mode override)."""
    user = await require_auth(request)
    _guard(user)
    db = get_db()
    ctx = await resolve_override(request, user, db)
    if not ctx:
        return {'active': False, 'override_header': OVERRIDE_HEADER}
    return {'active': True, **ctx}


@router.get('/audit')
async def override_audit(request: Request):
    """Panel transparansi (keputusan 3a): dokumen apa saja yang diinput staf DA.

    `?vendor_id=` menyaring satu vendor. Bila header override aktif, vendornya
    otomatis mengikuti vendor yang sedang diwakili.
    """
    user = await require_auth(request)
    _guard(user)
    db = get_db()
    ctx = await resolve_override(request, user, db)
    vendor_id = ctx['vendor_id'] if ctx else (request.query_params.get('vendor_id') or '')
    try:
        limit = min(200, max(1, int(request.query_params.get('limit') or 50)))
    except ValueError:
        limit = 50

    entries, totals = [], {'staff': 0, 'vendor': 0}
    for coll, label, num_field, prefix in _AUDIT_SOURCES:
        base = await _vendor_filter(db, coll, vendor_id)
        staff_flag = f'{prefix}entered_by_staff'
        by_field = f'{prefix}entered_by'
        role_field = f'{prefix}entered_by_role'
        date_field = f'{prefix}entered_at'

        staff_n = await db[coll].count_documents({**base, staff_flag: True})
        all_n = await db[coll].count_documents(base)
        totals['staff'] += staff_n
        totals['vendor'] += max(0, all_n - staff_n)

        docs = await db[coll].find(
            {**base, staff_flag: True}, {'_id': 0}
        ).sort(date_field, -1).to_list(limit)
        for d in docs:
            entries.append({
                'module': label,
                'collection': coll,
                'doc_id': d.get('id', ''),
                'reference': d.get(num_field) or d.get('id', ''),
                'entered_by': d.get(by_field, ''),
                'entered_by_role': d.get(role_field, ''),
                'entered_at': serialize_doc(d.get(date_field)),
                'vendor_id': d.get('vendor_id', '') or d.get(f'{prefix}on_behalf_of_vendor', ''),
                'vendor_name': (d.get('vendor_name', '')
                                or d.get(f'{prefix}on_behalf_of_vendor_name', '')),
            })

    entries.sort(key=lambda e: (e['entered_at'] or ''), reverse=True)
    return {
        'vendor_id': vendor_id,
        'entries': entries[:limit],
        'totals': totals,
        'total_entries': len(entries),
    }


# ═══════════════════════════════════════════════════════════════════════════
# REKAP HARIAN (2026-08-08) — "vendor mana yang belum diisi hari ini"
# ═══════════════════════════════════════════════════════════════════════════
# Tiga endpoint di bawah SEMUANYA memakai `core.cmt_daily_recap.build_recap()`.
# Tidak ada satu pun yang menghitung ulang: layar, berkas Excel/PDF, dan sasaran
# tombol reminder WAJIB menyebut angka yang sama, kalau tidak staf akan berdebat
# dengan lampirannya sendiri.
#
# Catatan: rekap SENGAJA mengabaikan header `X-CMT-Override-Vendor` — ini
# pandangan LINTAS vendor milik staf. Akun vendor tetap ditolak oleh `_guard()`.

def _recap_day(request: Request):
    try:
        return parse_day(request.query_params.get('date'))
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get('/daily-recap')
async def daily_recap(request: Request):
    """Rekap harian pengisian vendor CMT (keputusan owner 1c/2a/3a/4a).

    Query: ``?date=YYYY-MM-DD`` (default hari ini menurut **WIB**),
    ``?include_inactive=true`` untuk ikut menampilkan vendor non-aktif.
    """
    user = await require_auth(request)
    _guard(user)
    db = get_db()
    include_inactive = (request.query_params.get('include_inactive') or '').lower() == 'true'
    recap = await build_recap(db, _recap_day(request), include_inactive=include_inactive)
    return serialize_doc(recap)


@router.post('/daily-recap/remind')
async def daily_recap_remind(request: Request):
    """Kirim reminder ke vendor yang **belum diisi** pada tanggal rekap.

    Body (semua opsional)::

        {"date": "2026-08-08", "vendor_ids": ["..."], "message": "..."}

    * tanpa ``vendor_ids`` → sasarannya SEMUA vendor berstatus ``pending``
      (bukan ``partial``: vendor itu sudah menyetor hari ini, menegurnya membuat
      staf tidak dipercaya — lihat ``pending_vendor_rows``);
    * **idempoten**: satu vendor hanya dapat SATU reminder rekap per tanggal.
      Tanpa ini, tombol yang diklik dua kali (atau dua staf yang sama-sama
      rajin) akan membanjiri inbox vendor dan reminder rekap kehilangan arti.
    """
    user = await require_auth(request)
    _guard(user)
    db = get_db()
    body = {}
    try:
        body = await request.json()
    except Exception:
        body = {}

    try:
        day = parse_day((body or {}).get('date'))
    except ValueError as e:
        raise HTTPException(400, str(e))
    day_str = day.strftime('%Y-%m-%d')

    # F12 — pengirimannya SSOT di `core/cmt_daily_recap.send_recap_reminders()`
    # supaya tombol ini dan penjadwal 16:00 WIB memakai aturan idempotensi yang
    # SAMA. Kalau penjadwal menyalin logikanya, vendor akan menerima teguran
    # dobel dan reminder rekap berhenti dibaca.
    try:
        result = await send_recap_reminders(
            db, day,
            vendor_ids=(body or {}).get('vendor_ids'),
            message=(body or {}).get('message') or '',
            actor=user, source='manual')
    except ValueError as e:
        raise HTTPException(404, str(e)) from None

    if result['sent']:
        await log_activity(user['id'], user.get('name', ''), 'Create', 'Reminder',
                           f"Rekap harian {day_str}: kirim reminder ke "
                           f"{len(result['sent'])} vendor CMT")

    return JSONResponse(result, status_code=201 if result['sent'] else 200)


@router.get('/daily-recap/export')
async def daily_recap_export(request: Request):
    """Rekap harian sebagai lampiran: ``?format=xlsx`` (default) atau ``pdf``.

    Isinya dibangun dari `build_recap()` yang SAMA dengan layar — supervisor bisa
    mencetaknya untuk briefing pagi tanpa takut angkanya berbeda.
    """
    user = await require_auth(request)
    _guard(user)
    db = get_db()
    fmt = (request.query_params.get('format') or 'xlsx').lower()
    if fmt not in ('xlsx', 'pdf'):
        raise HTTPException(400, "Parameter format hanya 'xlsx' atau 'pdf'.")

    day = _recap_day(request)
    recap = await build_recap(db, day)

    from utils import cmt_recap_export as export
    from utils.pdf_common import get_company_profile
    company = (await get_company_profile(db)).get('company_name') or 'CV. Dewi Aditya'

    try:
        if fmt == 'pdf':
            data, fname = export.build_pdf(company=company, recap=recap)
            media = 'application/pdf'
        else:
            data, fname = export.build_xlsx(company=company, recap=recap)
            media = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    except Exception as e:  # noqa: BLE001
        _log.exception('[cmt-daily-recap-export] gagal membuat rapor')
        raise HTTPException(500, f'Gagal membuat rapor rekap harian: {e}')

    return StreamingResponse(
        io.BytesIO(data), media_type=media,
        headers={'Content-Disposition': f'attachment; filename="{fname}"',
                 'Access-Control-Expose-Headers': 'Content-Disposition'},
    )



# ═══════════════════════════════════════════════════════════════════════════
# REKAP MINGGUAN (fase 4) — 7 hari bergulir
# ═══════════════════════════════════════════════════════════════════════════
# Kenapa jendela BERGULIR, bukan Senin–Minggu (keputusan owner 1): pertanyaan yang
# dijawab layar ini adalah "vendor mana yang BELAKANGAN INI sering bolong". Versi
# Senin–Minggu membuat setiap Senin pagi menampilkan pekan yang baru berumur satu
# hari — tidak bisa dipakai mengambil keputusan.
#
# `date` (atau `end`) = tanggal TERAKHIR jendela, bukan awalnya. Ini disengaja
# supaya tombol ◀ / ▶ di layar memindahkan jendela dengan satu parameter yang
# sama seperti tab Harian, dan supaya default (tanpa parameter) = 7 hari yang
# berakhir HARI INI.

def _week_params(request: Request) -> tuple:
    """``(end_day, days, include_inactive)`` dari query string."""
    raw_end = (request.query_params.get('date')
               or request.query_params.get('end')
               or request.query_params.get('end_date'))
    try:
        end_day = parse_day(raw_end)
    except ValueError as e:
        raise HTTPException(400, str(e))

    raw_days = request.query_params.get('days')
    days = WEEK_DAYS
    if raw_days:
        try:
            days = int(str(raw_days).strip())
        except (TypeError, ValueError):
            raise HTTPException(400, 'Parameter days harus angka (mis. 7).')
        if days < 1 or days > MAX_WEEK_DAYS:
            raise HTTPException(400, f'Parameter days harus 1..{MAX_WEEK_DAYS}.')

    include_inactive = (request.query_params.get('include_inactive') or '').lower() == 'true'
    return end_day, days, include_inactive


@router.get('/weekly-recap')
async def weekly_recap(request: Request):
    """**Rekap Mingguan** — 7 hari bergulir yang BERAKHIR di ``?date=YYYY-MM-DD``.

    Query: ``?date=`` (default hari ini WIB), ``?days=`` (1..31, default 7),
    ``?include_inactive=true``, ``?compare=true`` (F12 — sertakan perbandingan
    dengan jendela sebelumnya).

    Angkanya bukan perhitungan kedua: :func:`core.cmt_daily_recap.build_week`
    memanggil ``build_recap()`` untuk tiap hari, jadi tab Mingguan dan tab Harian
    tidak mungkin berbeda untuk tanggal yang sama.

    **Kenapa `compare` OPT-IN dan bukan selalu?** Perbandingan berarti membangun
    DUA jendela (14 hari), jadi biayanya dua kali. Gate `INV-REKAP` RK-27 menjaga
    agar layar mingguan tidak lebih mahal daripada 7× rekap harian; menyalakannya
    diam-diam untuk semua pemanggil akan melanggar jaminan itu tanpa ada yang
    memutuskannya. Layar meminta perbandingan hanya ketika panelnya dibuka.
    """
    user = await require_auth(request)
    _guard(user)
    db = get_db()
    end_day, days, include_inactive = _week_params(request)
    want_compare = (request.query_params.get('compare') or '').lower() in ('1', 'true', 'yes')
    if want_compare:
        cmp_res = await build_week_comparison(
            db, end_day, include_inactive=include_inactive, days=days)
        payload = dict(cmp_res['current'])
        payload['comparison'] = {
            'previous': cmp_res['previous'], 'delta': cmp_res['delta'],
            'per_vendor': cmp_res['per_vendor'], 'movers': cmp_res['movers'],
            'new_vendors': cmp_res['new_vendors'],
            'comparable': cmp_res['comparable'],
            'note': cmp_res['note'],
        }
        return serialize_doc(payload)
    week = await build_week(db, end_day, include_inactive=include_inactive, days=days)
    return serialize_doc(week)


@router.get('/weekly-recap/export')
async def weekly_recap_export(request: Request):
    """Rekap mingguan sebagai lampiran: ``?format=xlsx`` (default) atau ``pdf``.

    Dibangun dari `build_week()` yang SAMA dengan layar — supervisor bisa
    mencetaknya untuk rapat mingguan tanpa takut angkanya bergeser.

    ``?compare=true`` menambahkan bagian perbandingan antar-pekan yang sama
    dengan panel di layar. **Kenapa lampirannya ikut punya:** legenda di layar
    menjanjikan "Excel/PDF isinya sama dengan layar ini". Begitu layar punya
    panel naik/turun sementara lampirannya tidak, janji itu jadi bohong — dan
    yang dibawa ke rapat justru lampirannya, jadi rapatnya kehilangan tepat
    bagian yang dipakai mengambil keputusan. Peringkat "paling memburuk" diambil
    dari SSOT `build_week_comparison()` yang sama, jadi layar dan lampiran tidak
    bisa menunjuk vendor terburuk yang berbeda.
    """
    user = await require_auth(request)
    _guard(user)
    db = get_db()
    fmt = (request.query_params.get('format') or 'xlsx').lower()
    if fmt not in ('xlsx', 'pdf'):
        raise HTTPException(400, "Parameter format hanya 'xlsx' atau 'pdf'.")

    end_day, days, include_inactive = _week_params(request)
    want_compare = (request.query_params.get('compare') or '').lower() in ('1', 'true', 'yes')
    if want_compare:
        cmp_res = await build_week_comparison(
            db, end_day, include_inactive=include_inactive, days=days)
        week = dict(cmp_res['current'])
        week['comparison'] = {
            'previous': cmp_res['previous'], 'delta': cmp_res['delta'],
            'per_vendor': cmp_res['per_vendor'], 'movers': cmp_res['movers'],
            'new_vendors': cmp_res['new_vendors'],
            'comparable': cmp_res['comparable'], 'note': cmp_res['note'],
        }
    else:
        week = await build_week(db, end_day, include_inactive=include_inactive, days=days)

    from utils import cmt_recap_export as export
    from utils.pdf_common import get_company_profile
    company = (await get_company_profile(db)).get('company_name') or 'CV. Dewi Aditya'

    try:
        if fmt == 'pdf':
            data, fname = export.build_week_pdf(company=company, week=week)
            media = 'application/pdf'
        else:
            data, fname = export.build_week_xlsx(company=company, week=week)
            media = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    except Exception as e:  # noqa: BLE001
        _log.exception('[cmt-weekly-recap-export] gagal membuat rapor')
        raise HTTPException(500, f'Gagal membuat rapor rekap mingguan: {e}')

    return StreamingResponse(
        io.BytesIO(data), media_type=media,
        headers={'Content-Disposition': f'attachment; filename="{fname}"',
                 'Access-Control-Expose-Headers': 'Content-Disposition'},
    )

