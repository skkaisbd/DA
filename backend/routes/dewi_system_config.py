"""
CV. Dewi Aditya — System Configuration API
Generic key/value settings stored in MongoDB, editable via UI.

Used for:
- Maklon: QC reject threshold, invoice prefix, tax %, payment terms default
- Notifications: WA/Telegram bot tokens, channels (configurable, NOT hardcoded)
- Marketplace: Shopee/Tokopedia API credentials (configurable)

Collection: dewi_system_config
Schema: { key, value, category, label, description, data_type, is_secret, updated_at, updated_by }
"""
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional, Any
from datetime import datetime, timezone
from database import get_db
from auth import require_auth

router = APIRouter(prefix='/api/dewi/system/config', tags=['Dewi-System-Config'])

# ══════════════════════════════════════════════════════════════════════════════
# DEFAULT CONFIG SCHEMA (for initial render in UI)
# ══════════════════════════════════════════════════════════════════════════════

DEFAULT_CONFIGS = [
    # Maklon / Invoice / QC
    {
        'key': 'maklon_invoice_prefix',
        'value': 'INV-MKL',
        'category': 'maklon',
        'label': 'Prefix Invoice Maklon',
        'description': 'Prefix untuk nomor invoice order maklon. Contoh INV-MKL → INV-MKL-2026-0001',
        'data_type': 'string',
        'is_secret': False,
    },
    {
        'key': 'maklon_tax_pct',
        'value': 11.0,
        'category': 'maklon',
        'label': 'PPN Invoice Maklon (%)',
        'description': 'Persentase PPN default yang diterapkan pada invoice maklon',
        'data_type': 'number',
        'is_secret': False,
    },
    {
        'key': 'maklon_payment_terms_default',
        'value': 'net_30',
        'category': 'maklon',
        'label': 'Payment Terms Default',
        'description': 'Termin pembayaran default: net_7 | net_14 | net_30 | net_60',
        'data_type': 'string',
        'is_secret': False,
    },
    {
        'key': 'maklon_qc_reject_threshold_pct',
        'value': 5.0,
        'category': 'maklon',
        'label': 'QC Reject Threshold (%)',
        'description': 'Ambang batas reject rate QC maklon. Di atas nilai ini akan memicu alert',
        'data_type': 'number',
        'is_secret': False,
    },
    # CMT Operasional (Maklon CMT Operasional Plan — Fase 0 fondasi)
    {
        'key': 'maklon_cmt_buffer_days',
        'value': 3,
        'category': 'maklon',
        'label': 'Buffer Target CMT (hari)',
        'description': 'Selisih hari antara Deadline Mitra/Buyer (delivery_deadline) dan Target CMT. '
                       'Target CMT = delivery_deadline − buffer. Dipakai monitoring KEJAR CMT.',
        'data_type': 'number',
        'is_secret': False,
    },
    {
        'key': 'maklon_cmt_late_grace_days',
        'value': 5,
        'category': 'maklon',
        'label': 'Grace Telat CMT (hari, H+N)',
        'description': 'Ambang "TELAT": job dianggap telat bila melewati Target CMT lebih dari N hari '
                       '(mis. H+5). Di bawahnya berstatus "mendekati deadline".',
        'data_type': 'number',
        'is_secret': False,
    },
    {
        'key': 'maklon_permak_return_grace_days',
        'value': 3,
        'category': 'maklon',
        'label': 'Grace Kembali Permak (hari, H+N)',
        'description': 'Penanda H+N untuk permak/retur ke CMT: bila melewati return_deadline lebih dari N hari, '
                       'permak ditandai perlu tindakan (mis. H+3).',
        'data_type': 'number',
        'is_secret': False,
    },

    # HPP cost components (configurable, used for HPP calculation)
    {
        'key': 'hpp_overhead_pct',
        'value': 15.0,
        'category': 'hpp',
        'label': 'HPP Overhead (%)',
        'description': 'Persentase overhead pabrik dari biaya langsung (material + upah)',
        'data_type': 'number',
        'is_secret': False,
    },
    {
        'key': 'hpp_profit_margin_pct',
        'value': 20.0,
        'category': 'hpp',
        'label': 'Target Margin Profit (%)',
        'description': 'Target margin profit default untuk kalkulasi harga jual',
        'data_type': 'number',
        'is_secret': False,
    },

    # Notifications (configurable, not hardcoded)
    {
        'key': 'notification_whatsapp_enabled',
        'value': False,
        'category': 'notification',
        'label': 'Aktifkan Notifikasi WhatsApp',
        'description': 'Enable/disable integrasi WhatsApp (Twilio/WABA) untuk notifikasi',
        'data_type': 'boolean',
        'is_secret': False,
    },
    {
        'key': 'notification_whatsapp_provider',
        'value': 'twilio',
        'category': 'notification',
        'label': 'WhatsApp Provider',
        'description': 'twilio | waba_cloud | wabots',
        'data_type': 'string',
        'is_secret': False,
    },
    {
        'key': 'notification_whatsapp_api_key',
        'value': '',
        'category': 'notification',
        'label': 'WhatsApp API Key / Token',
        'description': 'Token atau Auth Key provider WhatsApp',
        'data_type': 'string',
        'is_secret': True,
    },
    {
        'key': 'notification_whatsapp_sender',
        'value': '',
        'category': 'notification',
        'label': 'Nomor / Sender WhatsApp',
        'description': 'Nomor sender terdaftar, contoh whatsapp:+6281xxxxxxx',
        'data_type': 'string',
        'is_secret': False,
    },
    {
        'key': 'notification_telegram_enabled',
        'value': False,
        'category': 'notification',
        'label': 'Aktifkan Notifikasi Telegram',
        'description': 'Enable/disable Telegram Bot untuk notifikasi',
        'data_type': 'boolean',
        'is_secret': False,
    },
    {
        'key': 'notification_telegram_bot_token',
        'value': '',
        'category': 'notification',
        'label': 'Telegram Bot Token',
        'description': 'Token dari @BotFather',
        'data_type': 'string',
        'is_secret': True,
    },
    {
        'key': 'notification_telegram_chat_id',
        'value': '',
        'category': 'notification',
        'label': 'Telegram Chat ID Default',
        'description': 'Chat ID tujuan notifikasi (grup/user)',
        'data_type': 'string',
        'is_secret': False,
    },

    # Marketplace integration (Phase 5 — configurable di sini supaya tidak hardcode)
    {
        'key': 'marketplace_shopee_enabled',
        'value': False,
        'category': 'marketplace',
        'label': 'Aktifkan Integrasi Shopee',
        'description': 'Enable Shopee Open API',
        'data_type': 'boolean',
        'is_secret': False,
    },
    {
        'key': 'marketplace_shopee_partner_id',
        'value': '',
        'category': 'marketplace',
        'label': 'Shopee Partner ID',
        'description': 'Partner ID dari Shopee Open Platform',
        'data_type': 'string',
        'is_secret': False,
    },
    {
        'key': 'marketplace_shopee_partner_key',
        'value': '',
        'category': 'marketplace',
        'label': 'Shopee Partner Key',
        'description': 'Partner Key (secret) dari Shopee Open Platform',
        'data_type': 'string',
        'is_secret': True,
    },
    {
        'key': 'marketplace_tokopedia_enabled',
        'value': False,
        'category': 'marketplace',
        'label': 'Aktifkan Integrasi Tokopedia',
        'description': 'Enable Tokopedia API',
        'data_type': 'boolean',
        'is_secret': False,
    },
    {
        'key': 'marketplace_tokopedia_client_id',
        'value': '',
        'category': 'marketplace',
        'label': 'Tokopedia Client ID',
        'description': 'Client ID aplikasi Tokopedia',
        'data_type': 'string',
        'is_secret': False,
    },
    {
        'key': 'marketplace_tokopedia_client_secret',
        'value': '',
        'category': 'marketplace',
        'label': 'Tokopedia Client Secret',
        'description': 'Client Secret aplikasi Tokopedia',
        'data_type': 'string',
        'is_secret': True,
    },
]


class ConfigUpdate(BaseModel):
    value: Any

# ══════════════════════════════════════════════════════════════════════════════
# UTILS
# ══════════════════════════════════════════════════════════════════════════════

def _mask_secret(doc: dict) -> dict:
    """Mask secret values for non-admin returns."""
    doc.pop('_id', None)
    if doc.get('is_secret') and doc.get('value'):
        val = str(doc['value'])
        if len(val) > 4:
            doc['value_masked'] = '•' * (len(val) - 4) + val[-4:]
        else:
            doc['value_masked'] = '••••'
        # Keep original value only for admins (caller can check role)
    return doc

async def ensure_defaults(db):
    """Make sure all default configs exist (idempotent)."""
    existing_keys = set()
    async for doc in db.dewi_system_config.find({}, {'key': 1, '_id': 0}):
        existing_keys.add(doc['key'])

    to_insert = []
    now = datetime.now(timezone.utc)
    for cfg in DEFAULT_CONFIGS:
        if cfg['key'] not in existing_keys:
            to_insert.append({
                **cfg,
                'updated_at': now,
                'updated_by': 'system_init',
            })
    if to_insert:
        await db.dewi_system_config.insert_many(to_insert)
    return len(to_insert)

async def get_config_value(db, key: str, default: Any = None):
    """Helper for other modules to read a config value safely."""
    doc = await db.dewi_system_config.find_one({'key': key})
    if not doc or doc.get('value') is None:
        return default
    return doc['value']

# ══════════════════════════════════════════════════════════════════════════════
# ROUTES
# ══════════════════════════════════════════════════════════════════════════════

@router.get('')
async def list_configs(
    category: Optional[str] = None,
    user: dict = Depends(require_auth),
):
    db = get_db()
    await ensure_defaults(db)

    is_admin = user.get('role') in ('admin', 'superadmin') or 'admin' in (user.get('roles') or [])
    query = {'category': category} if category else {}
    items = await db.dewi_system_config.find(query).sort([('category', 1), ('key', 1)]).to_list(length=500)

    out = []
    for doc in items:
        cleaned = {**doc}
        _mask_secret(cleaned)
        # Hide raw secret value if not admin
        if cleaned.get('is_secret') and not is_admin:
            cleaned.pop('value', None)
        out.append(cleaned)
    return out

@router.get('/categories')
async def list_categories(user: dict = Depends(require_auth)):
    db = get_db()
    await ensure_defaults(db)
    cats = await db.dewi_system_config.distinct('category')
    return sorted(cats)

@router.get('/{key}')
async def get_config(key: str, user: dict = Depends(require_auth)):
    db = get_db()
    await ensure_defaults(db)
    doc = await db.dewi_system_config.find_one({'key': key})
    if not doc:
        raise HTTPException(404, f'Config {key} tidak ditemukan')
    is_admin = user.get('role') in ('admin', 'superadmin') or 'admin' in (user.get('roles') or [])
    doc.pop('_id', None)
    _mask_secret(doc)
    if doc.get('is_secret') and not is_admin:
        doc.pop('value', None)
    return doc

@router.put('/{key}')
async def update_config(key: str, payload: ConfigUpdate, user: dict = Depends(require_auth)):
    db = get_db()
    existing = await db.dewi_system_config.find_one({'key': key})
    if not existing:
        raise HTTPException(404, f'Config {key} tidak ditemukan')

    # Coerce value to expected data_type
    dt = existing.get('data_type', 'string')
    new_value = payload.value
    try:
        if dt == 'number':
            new_value = float(new_value)
        elif dt == 'boolean':
            if isinstance(new_value, str):
                new_value = new_value.lower() in ('true', '1', 'yes', 'on')
            else:
                new_value = bool(new_value)
        elif dt == 'string':
            new_value = '' if new_value is None else str(new_value)
    except (ValueError, TypeError):
        raise HTTPException(400, f'Value tidak valid untuk data_type {dt}')

    await db.dewi_system_config.update_one(
        {'key': key},
        {'$set': {
            'value': new_value,
            'updated_at': datetime.now(timezone.utc),
            'updated_by': user.get('name', 'System'),
        }}
    )
    return {'message': f'Config {key} diperbarui'}

class BulkUpdateIn(BaseModel):
    """Generic key/value bulk update. Accepts arbitrary additional fields."""
    model_config = {'extra': 'allow'}


@router.post('/bulk')
async def bulk_update(payload: BulkUpdateIn, user: dict = Depends(require_auth)):
    """Update multiple configs in one call. payload = {key: value, ...}"""
    db = get_db()
    now = datetime.now(timezone.utc)
    updated = 0
    errors = []
    keys_list = list(payload.model_dump().keys())
    # Batch prefetch existing configs for all keys
    existing_configs_map = {}
    if keys_list:
        async for d in db.dewi_system_config.find(
            {'key': {'$in': keys_list}}, {'_id': 0}
        ):
            existing_configs_map[d['key']] = d
    for key, value in payload.model_dump().items():
        existing = existing_configs_map.get(key)
        if not existing:
            errors.append(f'{key}: tidak ditemukan')
            continue
        dt = existing.get('data_type', 'string')
        new_value = value
        try:
            if dt == 'number':
                new_value = float(new_value) if new_value != '' else 0
            elif dt == 'boolean':
                if isinstance(new_value, str):
                    new_value = new_value.lower() in ('true', '1', 'yes', 'on')
                else:
                    new_value = bool(new_value)
            elif dt == 'string':
                new_value = '' if new_value is None else str(new_value)
        except (ValueError, TypeError):
            errors.append(f'{key}: invalid type')
            continue
        await db.dewi_system_config.update_one(
            {'key': key},
            {'$set': {
                'value': new_value,
                'updated_at': now,
                'updated_by': user.get('name', 'System'),
            }}
        )
        updated += 1
    return {'updated': updated, 'errors': errors}
