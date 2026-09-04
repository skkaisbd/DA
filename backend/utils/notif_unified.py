"""
P3 TD-010 Part B — Unified Notifications Helper (Session #11.12)
================================================================
Single SSOT helper for the `notifications` collection.

After Session #11.12 (TD-010 Phase B), ALL legacy notification writers
(dewi_notifications, rahaza_notifications, collab_notifications,
marketing_livehost_notifications) have been refactored to call
`notif_insert()` directly. The 4 legacy collections are now empty
and scheduled for removal after a 1-week monitor period via
`migrations/drop_legacy_notif_collections.py`.

This module also exposes BACKWARD-COMPAT reshape helpers used by
the 4 legacy routers to keep their public response schema unchanged
while reading from the SSOT.
"""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Optional, Any, List
import uuid


VALID_TYPES = {'dewi', 'rahaza', 'collab', 'marketing_livehost'}
VALID_SEVERITIES = {'info', 'success', 'warning', 'error'}
VALID_CHANNELS = {'in_app', 'whatsapp', 'email', 'sse'}


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ─────────────────────────────────────────────────────────────────────────────
# CORE INSERT
# ─────────────────────────────────────────────────────────────────────────────

async def notif_insert(
    db,
    *,
    type: str,
    body: str,
    id: Optional[str] = None,
    subtype: Optional[str] = None,
    severity: str = 'info',
    user_id: Optional[str] = None,
    title: Optional[str] = None,
    channel: str = 'in_app',
    recipient: Optional[str] = None,
    target_roles: Optional[List[str]] = None,
    target_user_ids: Optional[List[str]] = None,
    source_type: Optional[str] = None,
    source_id: Optional[str] = None,
    source_url: Optional[str] = None,
    source_ref: Optional[str] = None,
    client_id: Optional[str] = None,
    host_id: Optional[str] = None,
    meta: Optional[dict] = None,
    status: str = 'queued',
    sent_at: Optional[datetime] = None,
    read: bool = False,
    failed_reason: Optional[str] = None,
) -> str:
    """Insert a notification into the SSOT `notifications` collection.

    Returns the new notification id (UUID).

    Arguments:
        type:        Domain discriminator. Must be one of VALID_TYPES.
        body:        Main message body. Required.
        id:          Optional pre-allocated UUID (else generated).
        subtype:     Optional sub-classification (event_type, notif_type, etc.)
        severity:    info|success|warning|error
        user_id:     Recipient user id (None for broadcast)
        title:       Optional title/subject
        channel:     Delivery channel: in_app|whatsapp|email|sse
        recipient:   Phone/email when external delivery (whatsapp/email)
        source_*:    Linking info to originating resource
        client_id:   For dewi external client notifs
        host_id:     For marketing_livehost SSE
        meta:        Free-form metadata dict
        status:      queued|sent|failed|read
        sent_at:     Timestamp the notification was actually sent (channel ack)
        read:        Initial read state (default False)
        failed_reason: Error string when status='failed'
    """
    if type not in VALID_TYPES:
        raise ValueError(f'Invalid notification type {type!r}; must be one of {VALID_TYPES}')
    if severity not in VALID_SEVERITIES:
        severity = 'info'
    if channel not in VALID_CHANNELS:
        channel = 'in_app'

    # Target penerima kanonik di `meta` (dibaca `notif_audience_query`). Penulis
    # boleh mengirim lewat argumen ini ATAU lewat meta — keduanya digabung.
    meta = dict(meta or {})
    if target_roles:
        meta['target_roles'] = sorted({str(r).lower() for r in
                                       (list(meta.get('target_roles') or []) + list(target_roles))})
    elif meta.get('target_roles'):
        meta['target_roles'] = sorted({str(r).lower() for r in meta['target_roles']})
    if target_user_ids:
        meta['target_user_ids'] = sorted({str(u) for u in
                                          (list(meta.get('target_user_ids') or [])
                                           + list(target_user_ids))})
    doc = {
        'id':            id or str(uuid.uuid4()),
        'type':          type,
        'subtype':       subtype,
        'severity':      severity,
        'user_id':       user_id,
        'title':         title,
        'body':          body,
        'channel':       channel,
        'recipient':     recipient,
        'source_type':   source_type,
        'source_id':     source_id,
        'source_url':    source_url,
        'source_ref':    source_ref,
        'client_id':     client_id,
        'host_id':       host_id,
        'meta':          meta,
        'status':        status,
        'read':          read,
        'read_at':       None,
        'created_at':    _now(),
        'sent_at':       sent_at,
        'failed_reason': failed_reason,
    }
    await db.notifications.insert_one(doc)
    return doc['id']


# ─────────────────────────────────────────────────────────────────────────────
# AUDIENS / RBAC NOTIFIKASI — SATU MESIN untuk semua pembaca (2026-08-07)
#
# MASALAH YANG DIPERBAIKI (audit atas pertanyaan owner "jangan sampai role A
# menerima notifikasi role B"):
#   1. Dua konvensi penerima hidup bersama: penulis lama menaruh
#      `target_roles` / `target_user_ids` di akar dokumen, `publish_notification`
#      menaruhnya di `meta`, dan `notif_insert` memakai `user_id` per orang.
#      Setiap pembaca memakai aturannya sendiri ⇒ ada notifikasi yang tidak
#      pernah tampil, dan ada yang tampil ke orang yang tidak berhak.
#   2. Dokumen TANPA target dianggap "siaran untuk semua" ⇒ satu penulis yang
#      lupa mengisi target langsung membocorkan info lintas role.
#
# ATURAN SEKARANG (dipakai bel, inbox, hitungan belum dibaca, tandai dibaca):
#   penerima  = `user_id` == saya  ATAU  target_user_ids memuat saya
#               ATAU target_roles memuat role saya
#   tanpa target sama sekali = HANYA admin/owner/superadmin
#   status baca: dokumen personal → field `read`; dokumen banyak penerima →
#               `meta.read_by` (per orang, tidak saling menandai)
# ─────────────────────────────────────────────────────────────────────────────

NOTIF_SUPER_ROLES = {'superadmin', 'admin', 'owner'}
_EMPTY = {'$in': [None, []]}


def notif_user_id(user: dict) -> Optional[str]:
    return (user.get('id') or user.get('user_id') or user.get('sub')
            or user.get('email'))


def notif_recipient_or(user: dict) -> list:
    """Klausa $or Mongo: dokumen mana yang ditujukan kepada `user`."""
    uid = notif_user_id(user)
    role = (user.get('role') or '').lower()
    ors: list = [
        {'user_id': uid},
        {'target_user_ids': uid},
        {'meta.target_user_ids': uid},
    ]
    if role:
        ors += [{'target_roles': role}, {'meta.target_roles': role}]
    if role in NOTIF_SUPER_ROLES:
        ors.append({'user_id': None, 'target_user_ids': _EMPTY,
                    'target_roles': _EMPTY, 'meta.target_user_ids': _EMPTY,
                    'meta.target_roles': _EMPTY})
    return ors


def notif_audience_query(user: dict, extra: Optional[dict] = None) -> dict:
    """Query lengkap (audiens + belum dibuang) untuk daftar notifikasi user."""
    q: dict = {
        '$or': notif_recipient_or(user),
        'dismissed': {'$ne': True},
        'meta.dismissed': {'$ne': True},
    }
    if extra:
        q.update(extra)
    return q


def notif_visible_to(doc: dict, user: dict) -> bool:
    """Versi Python dari aturan audiens (untuk filter setelah query)."""
    if not doc:
        return False
    uid = notif_user_id(user)
    role = (user.get('role') or '').lower()
    meta = doc.get('meta') or {}
    if doc.get('user_id'):
        return doc.get('user_id') == uid
    users = list(doc.get('target_user_ids') or []) + list(meta.get('target_user_ids') or [])
    roles = [str(r).lower() for r in
             (list(doc.get('target_roles') or []) + list(meta.get('target_roles') or []))]
    if uid in users or role in roles:
        return True
    if not users and not roles:
        return role in NOTIF_SUPER_ROLES
    return False


def notif_is_unread_for(doc: dict, user: dict) -> bool:
    """Belum dibaca oleh user ini (personal: `read`; bersama: `meta.read_by`)."""
    uid = notif_user_id(user)
    meta = doc.get('meta') or {}
    if doc.get('user_id'):
        return not doc.get('read')
    read_by = list(meta.get('read_by') or []) + list(doc.get('read_by') or [])
    return uid not in read_by


async def notif_mark_read_for(db, notif_id: str, user: dict) -> bool:
    """Tandai dibaca HANYA untuk user ini (tidak menandai penerima lain)."""
    uid = notif_user_id(user)
    doc = await db.notifications.find_one({'id': notif_id}, {'_id': 0})
    if not doc or not notif_visible_to(doc, user):
        return False
    if doc.get('user_id'):
        res = await db.notifications.update_one(
            {'id': notif_id, 'user_id': uid},
            {'$set': {'read': True, 'read_at': _now()}})
        return res.matched_count > 0
    res = await db.notifications.update_one(
        {'id': notif_id}, {'$addToSet': {'meta.read_by': uid}})
    return res.matched_count > 0


async def notif_mark_all_read_for(db, user: dict, *, type: Optional[str] = None) -> int:
    """Tandai semua notifikasi milik user (personal + bersama) sebagai dibaca."""
    uid = notif_user_id(user)
    extra = {'type': type} if type else None
    rows = await db.notifications.find(
        notif_audience_query(user, extra), {'_id': 0, 'id': 1, 'user_id': 1, 'meta': 1,
                                            'read': 1, 'read_by': 1}).to_list(2000)
    personal = [r['id'] for r in rows if r.get('user_id') and notif_is_unread_for(r, user)]
    shared = [r['id'] for r in rows if not r.get('user_id') and notif_is_unread_for(r, user)]
    n = 0
    if personal:
        res = await db.notifications.update_many(
            {'id': {'$in': personal}}, {'$set': {'read': True, 'read_at': _now()}})
        n += res.modified_count
    if shared:
        res = await db.notifications.update_many(
            {'id': {'$in': shared}}, {'$addToSet': {'meta.read_by': uid}})
        n += res.modified_count
    return n


async def notif_count_unread_for(db, user: dict, *, type: Optional[str] = None) -> int:
    extra = {'type': type} if type else None
    rows = await db.notifications.find(
        notif_audience_query(user, extra),
        {'_id': 0, 'user_id': 1, 'read': 1, 'meta': 1, 'read_by': 1}).to_list(2000)
    return sum(1 for r in rows if notif_is_unread_for(r, user))


async def notif_list_for(db, user: dict, *, type: Optional[str] = None,
                         severity: Optional[str] = None, unread_only: bool = False,
                         limit: int = 50, skip: int = 0) -> list:
    """Daftar notifikasi yang BOLEH dilihat user (audiens ditegakkan di query)."""
    extra: dict = {}
    if type:
        extra['type'] = type
    if severity:
        extra['severity'] = severity
    rows = await (db.notifications.find(notif_audience_query(user, extra), {'_id': 0})
                  .sort('created_at', -1).skip(skip).limit(limit * 3 if unread_only else limit)
                  ).to_list(limit * 3 if unread_only else limit)
    if unread_only:
        rows = [r for r in rows if notif_is_unread_for(r, user)][:limit]
    return rows


# ─────────────────────────────────────────────────────────────────────────────
# READ/COUNT/UPDATE
# ─────────────────────────────────────────────────────────────────────────────

async def notif_mark_read(db, notif_id: str, *, user_id: Optional[str] = None) -> bool:
    """Mark a notification as read. Returns True if a doc was updated.

    For single-recipient notifs (user_id-scoped), pass user_id for safety.
    For multi-recipient rahaza notifs, use update_meta to push to read_by[].
    """
    flt: dict = {'id': notif_id}
    if user_id:
        flt['user_id'] = user_id
    res = await db.notifications.update_one(
        flt,
        {'$set': {'read': True, 'read_at': _now()}},
    )
    return res.modified_count > 0


async def notif_count_unread(
    db, *, user_id: Optional[str] = None, type: Optional[str] = None,
) -> int:
    flt: dict = {'read': False}
    if user_id:
        flt['user_id'] = user_id
    if type:
        flt['type'] = type
    return await db.notifications.count_documents(flt)


async def notif_list(
    db,
    *,
    user_id: Optional[str] = None,
    type: Optional[str] = None,
    severity: Optional[str] = None,
    unread_only: bool = False,
    limit: int = 50,
    skip: int = 0,
) -> list:
    flt: dict = {}
    if user_id:
        flt['user_id'] = user_id
    if type:
        flt['type'] = type
    if severity:
        flt['severity'] = severity
    if unread_only:
        flt['read'] = False
    cursor = (
        db.notifications
        .find(flt, {'_id': 0})
        .sort('created_at', -1)
        .skip(skip)
        .limit(limit)
    )
    return [doc async for doc in cursor]


async def notif_find_one(db, flt: dict) -> Optional[dict]:
    """Get a single notif by arbitrary filter (excludes _id)."""
    return await db.notifications.find_one(flt, {'_id': 0})


async def notif_update_one(db, flt: dict, update: dict) -> int:
    """Apply a Mongo update operator on a single notif. Returns modified count."""
    res = await db.notifications.update_one(flt, update)
    return res.modified_count


async def notif_update_many(db, flt: dict, update: dict) -> int:
    """Apply a Mongo update on multiple notifs. Returns modified count."""
    res = await db.notifications.update_many(flt, update)
    return res.modified_count


async def notif_delete_one(db, flt: dict) -> int:
    """Delete a single notif. Returns delete count."""
    res = await db.notifications.delete_one(flt)
    return res.deleted_count


# ─────────────────────────────────────────────────────────────────────────────
# SERIALIZE
# ─────────────────────────────────────────────────────────────────────────────

def serialize_notif(doc: Any) -> dict:
    """Return a JSON-safe shallow copy (datetimes → ISO strings)."""
    if doc is None:
        return None  # type: ignore
    out = dict(doc)
    out.pop('_id', None)
    for k, v in out.items():
        if isinstance(v, datetime):
            out[k] = v.isoformat()
    return out


# ─────────────────────────────────────────────────────────────────────────────
# BACKWARD-COMPAT RESHAPE HELPERS
# Each helper converts an SSOT doc back into the legacy router's response
# schema so frontend clients continue to receive the same shape.
# ─────────────────────────────────────────────────────────────────────────────

def reshape_as_dewi(doc: dict) -> dict:
    """Reshape SSOT doc → legacy `dewi_notifications` schema."""
    if not doc:
        return {}
    out = dict(doc)
    out.pop('_id', None)
    meta = out.get('meta') or {}
    # Legacy field projection
    return {
        'id':            out.get('id'),
        'channel':       out.get('channel'),
        'recipient':     out.get('recipient'),
        'subject':       out.get('title'),
        'body':          out.get('body'),
        'event_type':    out.get('subtype'),
        'source_ref':    out.get('source_ref'),
        'client_id':     out.get('client_id'),
        'status':        out.get('status'),
        'meta':          {k: v for k, v in meta.items() if k not in ('sent_real', 'sent_mock')},
        'sent_real':     meta.get('sent_real', False),
        'sent_mock':     meta.get('sent_mock', False),
        'created_at':    _to_iso(out.get('created_at')),
        'sent_at':       _to_iso(out.get('sent_at')),
        'failed_reason': out.get('failed_reason'),
    }


def reshape_as_rahaza(doc: dict, *, current_user_id: Optional[str] = None) -> dict:
    """Reshape SSOT doc → legacy `rahaza_notifications` schema.

    Multi-recipient fields (target_roles, target_user_ids, read_by, dismissed,
    dedup_key) are stored in `meta` and reprojected to top-level.
    """
    if not doc:
        return {}
    out = dict(doc)
    out.pop('_id', None)
    meta = out.get('meta') or {}
    read_by = meta.get('read_by') or []
    shaped = {
        'id':              out.get('id'),
        'type':            out.get('subtype'),
        'severity':        out.get('severity'),
        'title':           out.get('title'),
        'message':         out.get('body'),
        'link_module':     meta.get('link_module'),
        'link_id':         out.get('source_id'),
        'target_roles':    meta.get('target_roles') or [],
        'target_user_ids': meta.get('target_user_ids') or [],
        'dedup_key':       meta.get('dedup_key'),
        'read_by':         read_by,
        'dismissed':       bool(meta.get('dismissed', False)),
        'created_at':      _to_iso(out.get('created_at')),
    }
    if current_user_id is not None:
        shaped['read'] = current_user_id in read_by
    return shaped


def reshape_as_collab(doc: dict) -> dict:
    """Reshape SSOT doc → legacy `collab_notifications` schema."""
    if not doc:
        return {}
    out = dict(doc)
    out.pop('_id', None)
    meta = out.get('meta') or {}
    return {
        'notification_id': out.get('id'),
        'user_id':         out.get('user_id'),
        'type':            out.get('subtype'),
        'icon':            meta.get('icon'),
        'title':           out.get('title'),
        'content':         out.get('body'),
        'source_type':     out.get('source_type'),
        'source_id':       out.get('source_id'),
        'source_url':      out.get('source_url'),
        'metadata':        {k: v for k, v in meta.items() if k != 'icon'},
        'read':            bool(out.get('read', False)),
        'read_at':         _to_iso(out.get('read_at')),
        'created_at':      _to_iso(out.get('created_at')),
    }


def reshape_as_livehost(doc: dict) -> dict:
    """Reshape SSOT doc → legacy `marketing_livehost_notifications` schema."""
    if not doc:
        return {}
    out = dict(doc)
    out.pop('_id', None)
    return {
        'id':         out.get('id'),
        'host_id':    out.get('host_id'),
        'type':       out.get('subtype'),
        'severity':   out.get('severity'),
        'title':      out.get('title'),
        'message':    out.get('body'),
        'link':       out.get('source_url'),
        'read':       bool(out.get('read', False)),
        'read_at':    _to_iso(out.get('read_at')),
        'created_at': _to_iso(out.get('created_at')),
    }


def _to_iso(v: Any) -> Optional[str]:
    """Convert datetime → ISO string; pass-through strings/None."""
    if v is None:
        return None
    if isinstance(v, datetime):
        return v.isoformat()
    return v


# ─────────────────────────────────────────────────────────────────────────────
# RAHAZA — multi-recipient helpers (read_by[], dedup, target filtering)
# ─────────────────────────────────────────────────────────────────────────────

async def rahaza_check_dedup(
    db, *, dedup_key: str, within_minutes: int = 10,
) -> Optional[dict]:
    """Check if an active rahaza notif with same dedup_key was created recently."""
    from datetime import timedelta
    if not dedup_key:
        return None
    since = _now() - timedelta(minutes=within_minutes)
    return await db.notifications.find_one({
        'type': 'rahaza',
        'meta.dedup_key': dedup_key,
        'meta.dismissed': {'$ne': True},
        'created_at': {'$gte': since},
    })


async def rahaza_mark_read_by(db, notif_id: str, user_id: str) -> int:
    """Add user_id to meta.read_by[] for a rahaza notif. Returns modified count."""
    res = await db.notifications.update_one(
        {'id': notif_id, 'type': 'rahaza'},
        {'$addToSet': {'meta.read_by': user_id}},
    )
    return res.modified_count


async def rahaza_mark_read_by_many(
    db, notif_ids: List[str], user_id: str,
) -> int:
    """Mark a batch of rahaza notifs as read by user."""
    if not notif_ids:
        return 0
    res = await db.notifications.update_many(
        {'id': {'$in': notif_ids}, 'type': 'rahaza'},
        {'$addToSet': {'meta.read_by': user_id}},
    )
    return res.modified_count


def rahaza_matches_user(notif: dict, user: dict) -> bool:
    """Return True if a rahaza notif (SSOT shape) is visible to user.

    2026-08-07: memakai aturan audiens tunggal (`notif_visible_to`). Dokumen
    tanpa target TIDAK lagi tampil ke semua role — hanya admin/owner.
    """
    return notif_visible_to(notif, user)
