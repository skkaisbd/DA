"""
CV. Dewi Aditya — Notification System (Phase 5 Enhanced)

Logs notifications + attempts real sending if provider is configured.
Fallback to MOCK (queued) when no provider set.

Providers supported:
- WhatsApp: Fonnte (https://fonnte.com) — popular in Indonesia
- Email: SMTP (Gmail, custom server)

P3 TD-010 Phase B (Session #11.12): This module previously wrote to the
legacy `dewi_notifications` collection. It now writes to the unified SSOT
`notifications` collection with `type='dewi'`. The public API surface
(endpoints, request/response shape) is preserved via reshape helpers.
"""
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from database import get_db
from auth import require_auth
from utils.helpers import _uid, _now
from utils.notif_unified import (
    notif_insert,
    notif_find_one,
    notif_update_one,
    notif_delete_one,
    reshape_as_dewi,
)
import logging

# ── RBAC outbox klien (2026-08-07) ───────────────────────────────────────────
# Outbox berisi seluruh pesan WhatsApp/email ke KLIEN dan bisa dipakai mengirim
# pesan baru. Sebelumnya cukup "sudah login" ⇒ operator pun bisa membaca &
# mengirim. Sekarang: izin `notifications.view` / manajemen (model fallback aman
# `routes.shared.can_act` — admin/owner selalu lolos).
OUTBOX_LEGACY_ROLES = (
    'superadmin', 'admin', 'owner', 'manager', 'director',
    'manager_keuangan', 'accounting', 'admin_maklon', 'manager_produksi', 'hr',
)


def _require_outbox_access(user: dict, what: str, *, manage: bool = False):
    from fastapi import HTTPException as _HTTPException
    from routes.shared import can_act
    keys = (('settings.manage', 'sysadmin.manage', 'maklon.manage')
            if manage else ('notifications.view', 'management.view', 'maklon.view'))
    if not can_act(user, *keys, legacy_roles=OUTBOX_LEGACY_ROLES):
        raise _HTTPException(403, f'Akses ditolak: tidak berhak {what}.')

logger = logging.getLogger(__name__)
router = APIRouter(prefix='/api/dewi/notifications', tags=['Dewi-Notifications'])

# P3 TD-010 Phase B (Session #11.12): writes go to unified SSOT.
logger.info(
    "[NOTIF-CONSOLIDATION] dewi_notifications router now writes/reads SSOT "
    "(collection: notifications, type='dewi')."
)


# ══════════════════════════════════════════════════════════════════════════════
# INTERNAL HELPERS
# ══════════════════════════════════════════════════════════════════════════════

async def _get_provider_config(db) -> dict:
    """Get provider config from DB (cached in collection)."""
    doc = await db.dewi_provider_config.find_one({'_type': 'main'})
    return doc or {}


async def _try_send_whatsapp(phone: str, body: str, config: dict) -> tuple:
    """
    Attempt to send WhatsApp via Fonnte API.
    Returns (success: bool, error: str | None).
    """
    api_key = str(config.get('whatsapp_api_key', '')).strip() if config.get('whatsapp_api_key') else ''
    if not api_key:
        return False, 'No WhatsApp API key configured'
    try:
        import httpx
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(
                'https://api.fonnte.com/send',
                headers={'Authorization': api_key},
                data={
                    'target': phone,
                    'message': body,
                    'countryCode': config.get('whatsapp_country_code', '62'),
                },
            )
            data = r.json()
            if r.status_code == 200 and data.get('status'):
                return True, None
            else:
                return False, data.get('reason', f'HTTP {r.status_code}')
    except Exception as e:
        return False, str(e)


async def _try_send_email(to_email: str, subject: str, body: str, config: dict) -> tuple:
    """
    Attempt to send email via SMTP.
    Returns (success: bool, error: str | None).
    """
    host = str(config.get('smtp_host', '')).strip() if config.get('smtp_host') else ''
    user = str(config.get('smtp_user', '')).strip() if config.get('smtp_user') else ''
    password = str(config.get('smtp_password', '')).strip() if config.get('smtp_password') else ''
    port = int(config.get('smtp_port', 587) or 587)
    from_email_raw = config.get('smtp_from_email', user)
    from_email = str(from_email_raw).strip() if from_email_raw else user

    if not (host and user and password):
        return False, 'SMTP not configured'
    try:
        import smtplib
        import ssl
        from email.mime.text import MIMEText
        from email.mime.multipart import MIMEMultipart

        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject or 'CV. Dewi Aditya Notification'
        msg['From'] = from_email
        msg['To'] = to_email
        msg.attach(MIMEText(body, 'plain', 'utf-8'))

        context = ssl.create_default_context()
        with smtplib.SMTP(host, port, timeout=10) as server:
            server.ehlo()
            server.starttls(context=context)
            server.login(user, password)
            server.sendmail(from_email, to_email, msg.as_string())
        return True, None
    except Exception as e:
        return False, str(e)


async def queue_notification(
    db,
    *,
    channel: str,
    recipient: str,
    body: str,
    event_type: str,
    subject: Optional[str] = None,
    source_ref: Optional[str] = None,
    client_id: Optional[str] = None,
    meta: Optional[Dict[str, Any]] = None,
    try_real: bool = True,
) -> str:
    """
    Insert notification record (into SSOT `notifications` with type='dewi')
    and attempt real sending if provider configured.
    Returns notif id.
    """
    config = await _get_provider_config(db)
    status = 'queued'
    sent_at = None
    failed_reason = None
    sent_real = False

    if try_real:
        if channel == 'whatsapp':
            ok, err = await _try_send_whatsapp(recipient, body, config)
            if ok:
                status = 'sent'
                sent_at = _now()
                sent_real = True
            elif err and err != 'No WhatsApp API key configured':
                status = 'failed'
                failed_reason = err
        elif channel == 'email':
            ok, err = await _try_send_email(recipient, subject or 'CV. Dewi Aditya', body, config)
            if ok:
                status = 'sent'
                sent_at = _now()
                sent_real = True
            elif err and err != 'SMTP not configured':
                status = 'failed'
                failed_reason = err

    sent_mock = (status == 'sent' and not sent_real)
    merged_meta = dict(meta or {})
    merged_meta['sent_real'] = sent_real
    merged_meta['sent_mock'] = sent_mock

    nid = await notif_insert(
        db,
        type='dewi',
        id=_uid(),
        body=body,
        subtype=event_type,
        title=subject,
        channel=channel,
        recipient=recipient,
        source_ref=source_ref,
        client_id=client_id,
        meta=merged_meta,
        status=status,
        sent_at=sent_at,
        failed_reason=failed_reason,
    )
    logger.info(f'[notif] {channel} to {recipient} [{event_type}] → {status}')
    return nid


async def queue_for_client(
    db,
    *,
    client_id: str,
    body: str,
    event_type: str,
    subject: Optional[str] = None,
    source_ref: Optional[str] = None,
    meta: Optional[Dict[str, Any]] = None,
) -> List[str]:
    """
    Resolve client contacts (email + phone) and queue WA + email notifs.
    Returns list of notif ids.
    """
    client = await db.dewi_maklon_clients.find_one({'id': client_id})
    if not client:
        logger.warning(f"[queue_for_client] Client {client_id} not found")
        return []
    out = []
    phone_raw = client.get('pic_phone')
    email_raw = client.get('pic_email')
    logger.info(f"[queue_for_client] Client {client_id}: phone={phone_raw}, email={email_raw}")
    phone = str(phone_raw).strip() if phone_raw else ''
    email = str(email_raw).strip() if email_raw else ''
    if phone:
        out.append(await queue_notification(
            db, channel='whatsapp', recipient=phone, body=body,
            event_type=event_type, source_ref=source_ref,
            client_id=client_id, meta=meta,
        ))
    if email:
        out.append(await queue_notification(
            db, channel='email', recipient=email,
            subject=subject or f'CV. Dewi Aditya — {event_type.replace("_", " ").title()}',
            body=body, event_type=event_type, source_ref=source_ref,
            client_id=client_id, meta=meta,
        ))
    return out


# ══════════════════════════════════════════════════════════════════════════════
# PYDANTIC MODELS
# ══════════════════════════════════════════════════════════════════════════════

class ManualNotifIn(BaseModel):
    channel: str = Field(..., description='whatsapp | email')
    recipient: str
    body: str
    subject: Optional[str] = None
    client_id: Optional[str] = None
    event_type: str = Field(default='manual')


class ProviderConfigIn(BaseModel):
    # WhatsApp (Fonnte)
    whatsapp_enabled: bool = False
    whatsapp_api_key: Optional[str] = None
    whatsapp_country_code: str = '62'
    whatsapp_sender_name: Optional[str] = None
    whatsapp_test_phone: Optional[str] = None
    # Email (SMTP)
    email_enabled: bool = False
    smtp_host: Optional[str] = None
    smtp_port: int = 587
    smtp_user: Optional[str] = None
    smtp_password: Optional[str] = None
    smtp_from_email: Optional[str] = None
    smtp_from_name: str = 'CV. Dewi Aditya'
    # FASE 10 — mode keamanan eksplisit. Pengirim lama SELALU memaksa STARTTLS + login,
    # sehingga relay internal (tanpa enkripsi / tanpa auth) tidak pernah bisa dipakai.
    # 'starttls' (587) | 'ssl' (465) | 'none' (server internal)
    smtp_security: str = 'starttls'
    smtp_test_email: Optional[str] = None
    # FASE 10 — rapor valuasi aksesoris otomatis (tanggal 1, 06:00 Asia/Jakarta)
    valuation_report_enabled: bool = True
    valuation_report_extra_emails: Optional[Any] = None
    # Event subscriptions
    notify_on_stage_change: bool = True
    notify_on_invoice_issued: bool = True
    notify_on_invoice_overdue: bool = True
    notify_on_sample_update: bool = True


# ══════════════════════════════════════════════════════════════════════════════
# PROVIDER CONFIG
# ══════════════════════════════════════════════════════════════════════════════

@router.get('/provider-config')
async def get_provider_config(user: dict = Depends(require_auth)):
    """Get current provider configuration (passwords masked)."""
    _require_outbox_access(user, 'melihat konfigurasi provider notifikasi')
    db = get_db()
    config = await _get_provider_config(db)
    # Mask sensitive fields
    masked = dict(config)
    masked.pop('_id', None)
    masked.pop('_type', None)
    if masked.get('whatsapp_api_key'):
        k = masked['whatsapp_api_key']
        masked['whatsapp_api_key'] = k[:4] + '****' + k[-4:] if len(k) > 8 else '****'
        masked['whatsapp_configured'] = True
    else:
        masked['whatsapp_configured'] = False
    if masked.get('smtp_password'):
        masked['smtp_password'] = '****'
        masked['email_configured'] = True
    else:
        masked['email_configured'] = False
    return masked


@router.put('/provider-config')
async def save_provider_config(payload: ProviderConfigIn, user: dict = Depends(require_auth)):
    """Save provider configuration."""
    _require_outbox_access(user, 'mengubah konfigurasi provider (SMTP/WhatsApp)', manage=True)
    db = get_db()
    existing = await db.dewi_provider_config.find_one({'_type': 'main'})
    update = payload.dict()
    update['_type'] = 'main'
    update['updated_at'] = _now()
    update['updated_by'] = user.get('name', 'System')

    # If password field is '****' (masked), keep existing value
    if existing:
        if update.get('smtp_password') == '****':
            update['smtp_password'] = existing.get('smtp_password', '')
        if update.get('whatsapp_api_key') and '****' in update['whatsapp_api_key']:
            update['whatsapp_api_key'] = existing.get('whatsapp_api_key', '')

    # FASE 10 — normalisasi: mode keamanan harus salah satu nilai yang didukung, dan
    # daftar email tambahan disimpan sebagai list bersih (boleh dikirim sebagai string).
    from services import accessory_valuation_mailer as _mailer
    from utils import email_sender as _email

    sec = str(update.get('smtp_security') or '').strip().lower()
    update['smtp_security'] = sec if sec in _email.VALID_SECURITY else 'starttls'
    update['valuation_report_extra_emails'] = _mailer.parse_extra_emails(
        update.get('valuation_report_extra_emails'))

    if existing:
        await db.dewi_provider_config.update_one({'_type': 'main'}, {'$set': update})
    else:
        await db.dewi_provider_config.insert_one(update)
    return {'message': 'Konfigurasi provider disimpan'}


@router.post('/provider-config/test')
async def test_provider(user: dict = Depends(require_auth)):
    """Test send a notification via configured provider."""
    _require_outbox_access(user, 'menguji kirim provider notifikasi', manage=True)
    db = get_db()
    config = await _get_provider_config(db)
    results = {}

    phone = config.get('whatsapp_test_phone') or user.get('phone', '')
    if config.get('whatsapp_api_key') and phone:
        ok, err = await _try_send_whatsapp(phone, 'Test pesan dari CV. Dewi Aditya. Konfigurasi WhatsApp berhasil!', config)
        results['whatsapp'] = {'success': ok, 'error': err}
    else:
        results['whatsapp'] = {'success': False, 'error': 'API key atau nomor test tidak dikonfigurasi'}

    email = config.get('smtp_test_email') or user.get('email', '')
    if config.get('smtp_host') and email:
        # FASE 10 — pakai pengirim baru: mendukung mode 'none'/'ssl'/'starttls' dan
        # server tanpa autentikasi, sehingga tombol Test benar-benar mencerminkan
        # jalur yang dipakai rapor valuasi bulanan (dengan lampiran).
        from utils import email_sender as _email

        res = await _email.send_email(
            config, to=email,
            subject='Test Email CV. Dewi Aditya',
            body_text=('Test email dari CV. Dewi Aditya. Konfigurasi SMTP berhasil!\n\n'
                       'Jalur ini juga dipakai untuk mengirim rapor valuasi persediaan '
                       'aksesoris berlampiran Excel & PDF setiap awal bulan.'),
        )
        results['email'] = {'success': res.get('ok'), 'error': res.get('error'),
                            'security': res.get('security'), 'host': res.get('host'),
                            'recipient': email}
    else:
        results['email'] = {'success': False, 'error': 'SMTP tidak dikonfigurasi atau email test tidak diisi'}

    return results


# ══════════════════════════════════════════════════════════════════════════════
# NOTIFICATION CRUD  (reads/writes SSOT `notifications` w/ type='dewi')
# ══════════════════════════════════════════════════════════════════════════════

def _dewi_filter(extra: Optional[dict] = None) -> dict:
    """Build a Mongo filter scoped to dewi notifications in the SSOT."""
    flt: dict = {'type': 'dewi'}
    if extra:
        for k, v in extra.items():
            if v is not None:
                flt[k] = v
    return flt


@router.get('')
async def list_notifications(
    status: Optional[str] = None,
    channel: Optional[str] = None,
    event_type: Optional[str] = None,
    limit: int = 100,
    user: dict = Depends(require_auth),
):
    """Outbox pesan ke KLIEN (WhatsApp/email) — data sensitif, khusus manajemen.

    2026-08-07: dulu terbuka untuk semua user login sehingga operator pun bisa
    membaca seluruh riwayat komunikasi ke klien.
    """
    _require_outbox_access(user, 'membuka outbox notifikasi klien')
    db = get_db()
    flt = _dewi_filter({
        'status': status,
        'channel': channel,
        'subtype': event_type,    # legacy `event_type` → SSOT `subtype`
    })
    cur = db.notifications.find(flt, {'_id': 0}).sort('created_at', -1).limit(limit)
    rows = [reshape_as_dewi(d) async for d in cur]
    return rows


@router.get('/summary')
async def summary(user: dict = Depends(require_auth)):
    _require_outbox_access(user, 'melihat ringkasan outbox notifikasi klien')
    db = get_db()
    total = await db.notifications.count_documents({'type': 'dewi'})
    by_status = {
        'queued':  await db.notifications.count_documents({'type': 'dewi', 'status': 'queued'}),
        'sent':    await db.notifications.count_documents({'type': 'dewi', 'status': 'sent'}),
        'failed':  await db.notifications.count_documents({'type': 'dewi', 'status': 'failed'}),
    }
    by_channel = {
        'whatsapp': await db.notifications.count_documents({'type': 'dewi', 'channel': 'whatsapp'}),
        'email':    await db.notifications.count_documents({'type': 'dewi', 'channel': 'email'}),
    }
    config = await _get_provider_config(db)
    return {
        'total': total,
        'by_status': by_status,
        'by_channel': by_channel,
        'whatsapp_configured': bool(config.get('whatsapp_api_key')),
        'email_configured': bool(config.get('smtp_host') and config.get('smtp_password')),
    }


@router.post('/manual')
async def send_manual(payload: ManualNotifIn, user: dict = Depends(require_auth)):
    _require_outbox_access(user, 'mengirim pesan manual ke klien', manage=True)
    db = get_db()
    nid = await queue_notification(
        db,
        channel=payload.channel,
        recipient=payload.recipient,
        body=payload.body,
        subject=payload.subject,
        event_type=payload.event_type,
        client_id=payload.client_id,
    )
    return {'id': nid, 'message': 'Notifikasi diqueue'}


@router.post('/bulk-send')
async def bulk_send_queued(user: dict = Depends(require_auth)):
    """Attempt to send all queued notifications via real provider."""
    _require_outbox_access(user, 'mengirim ulang seluruh notifikasi terqueue', manage=True)
    db = get_db()
    config = await _get_provider_config(db)
    cursor = db.notifications.find(
        {'type': 'dewi', 'status': 'queued'},
        {'_id': 0},
    )
    queued = [d async for d in cursor]
    results = {'attempted': len(queued), 'sent': 0, 'failed': 0, 'skipped': 0}

    for notif in queued:
        channel = notif.get('channel')
        recipient = notif.get('recipient', '')
        body = notif.get('body', '')
        subject = notif.get('title') or 'CV. Dewi Aditya'

        ok, err = False, 'No provider'
        if channel == 'whatsapp':
            ok, err = await _try_send_whatsapp(recipient, body, config)
        elif channel == 'email':
            ok, err = await _try_send_email(recipient, subject, body, config)

        if ok:
            await db.notifications.update_one(
                {'id': notif['id'], 'type': 'dewi'},
                {'$set': {
                    'status': 'sent',
                    'sent_at': _now(),
                    'meta.sent_real': True,
                    'meta.sent_mock': False,
                }},
            )
            results['sent'] += 1
        elif err in ('No WhatsApp API key configured', 'SMTP not configured', 'No provider'):
            results['skipped'] += 1
        else:
            await db.notifications.update_one(
                {'id': notif['id'], 'type': 'dewi'},
                {'$set': {'status': 'failed', 'failed_reason': err}},
            )
            results['failed'] += 1

    return results


@router.post('/{notif_id}/send')
async def mark_sent(notif_id: str, user: dict = Depends(require_auth)):
    """Try real send first; fallback to MOCK mark-as-sent."""
    _require_outbox_access(user, 'mengirim notifikasi ke klien', manage=True)
    db = get_db()
    notif = await notif_find_one(db, {'id': notif_id, 'type': 'dewi'})
    if not notif:
        raise HTTPException(404, 'Notifikasi tidak ditemukan')
    if notif.get('status') == 'sent':
        return {'message': 'Sudah pernah dikirim'}

    config = await _get_provider_config(db)
    ok, err = False, None
    channel = notif.get('channel')
    if channel == 'whatsapp':
        ok, err = await _try_send_whatsapp(notif['recipient'], notif['body'], config)
    elif channel == 'email':
        ok, err = await _try_send_email(
            notif['recipient'], notif.get('title', 'CV. Dewi Aditya'), notif['body'], config,
        )

    if ok:
        update = {
            'status': 'sent', 'sent_at': _now(),
            'meta.sent_real': True, 'meta.sent_mock': False,
        }
    else:
        # MOCK send
        update = {
            'status': 'sent', 'sent_at': _now(),
            'meta.sent_real': False, 'meta.sent_mock': True,
            'failed_reason': err,
        }

    await notif_update_one(db, {'id': notif_id, 'type': 'dewi'}, {'$set': update})
    return {
        'message': 'Dikirim via provider' if ok else 'Ditandai terkirim (MOCK)',
        'real': ok,
        'error': err if not ok else None,
    }


@router.post('/{notif_id}/retry')
async def retry(notif_id: str, user: dict = Depends(require_auth)):
    _require_outbox_access(user, 'mengirim ulang notifikasi klien', manage=True)
    db = get_db()
    notif = await notif_find_one(db, {'id': notif_id, 'type': 'dewi'})
    if not notif:
        raise HTTPException(404, 'Notifikasi tidak ditemukan')
    if notif.get('status') == 'sent':
        raise HTTPException(400, 'Sudah terkirim, tidak perlu retry')
    await notif_update_one(
        db, {'id': notif_id, 'type': 'dewi'},
        {'$set': {'status': 'queued', 'failed_reason': None}},
    )
    return {'message': 'Notifikasi diqueue ulang'}


@router.delete('/{notif_id}')
async def delete_notif(notif_id: str, user: dict = Depends(require_auth)):
    _require_outbox_access(user, 'menghapus notifikasi klien', manage=True)
    db = get_db()
    n = await notif_delete_one(db, {'id': notif_id, 'type': 'dewi'})
    if n == 0:
        raise HTTPException(404, 'Notifikasi tidak ditemukan')
    return {'message': 'Dihapus'}


@router.post('/scan-overdue')
async def scan_overdue(user: dict = Depends(require_auth)):
    """Scan invoices overdue dan queue notifikasi."""
    _require_outbox_access(user, 'menjalankan pemindaian invoice jatuh tempo', manage=True)
    from datetime import date
    db = get_db()
    today = date.today().isoformat()
    invoices = await db.dewi_maklon_invoices.find({
        'status': {'$in': ['issued', 'partial_paid', 'overdue']},
        'balance_amount': {'$gt': 0},
        'due_date': {'$lt': today},
    }).to_list(length=2000)

    queued = 0
    inv_ids = [inv.get('id') for inv in invoices if inv.get('id')]
    existing_notif_invs = set()
    if inv_ids:
        async for n in db.notifications.find(
            {
                'type': 'dewi',
                'subtype': 'invoice_overdue',
                'source_ref': {'$in': inv_ids},
            },
            {'_id': 0, 'source_ref': 1},
        ):
            existing_notif_invs.add(n['source_ref'])
    for inv in invoices:
        if inv.get('id') in existing_notif_invs:
            continue
        client_id = inv.get('client_id')
        if not client_id:
            continue
        body = (
            f"Invoice {inv.get('invoice_number')} sebesar Rp "
            f"{int(inv.get('balance_amount', 0)):,} sudah lewat jatuh tempo "
            f"({inv.get('due_date')}). Mohon segera lakukan pembayaran."
        ).replace(',', '.')
        ids = await queue_for_client(
            db, client_id=client_id,
            subject=f"[OVERDUE] Invoice {inv.get('invoice_number')}",
            body=body, event_type='invoice_overdue', source_ref=inv.get('id'),
            meta={'invoice_number': inv.get('invoice_number'), 'balance': inv.get('balance_amount')},
        )
        queued += len(ids)
    return {'queued': queued, 'invoices_checked': len(invoices)}
