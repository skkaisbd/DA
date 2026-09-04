"""
P3 TD-010 Part B — Unified Notifications Inbox (Session #11.11)
================================================================
SSOT-backed notifications API. Reads from the unified `notifications`
collection populated by:
  - New writes via `utils.notif_unified.notif_insert(...)`
  - One-time migration of legacy collections via
    `migrations/migrate_notifications_unification.py`

Endpoints:
  GET    /api/notifications/unified                         — list (filtered/paginated)
  GET    /api/notifications/unified/stats                   — counts per type / unread
  POST   /api/notifications/unified/{notif_id}/mark-read    — mark single as read
  POST   /api/notifications/unified/mark-all-read           — mark all (or by type)

Filtering:
  ?type=dewi|rahaza|collab|marketing_livehost
  ?severity=info|success|warning|error
  ?unread_only=true
  ?user_id=<id>   (defaults to current user when omitted; admin may pass any id)
  ?limit=50&skip=0

Legacy collections (`dewi_notifications`, `rahaza_notifications`,
`collab_notifications`, `marketing_livehost_notifications`) remain
accessible via their original endpoints for backward compatibility.
"""
from fastapi import APIRouter, Request, Query, HTTPException
from typing import Optional
import logging

from database import get_db
from auth import require_auth
from routes.shared import SUPER_ROLES
from utils.notif_unified import (
    notif_count_unread, notif_mark_read, serialize_notif,
    notif_audience_query, notif_count_unread_for, notif_is_unread_for,
    notif_list_for, notif_mark_all_read_for, notif_mark_read_for,
    VALID_TYPES, VALID_SEVERITIES,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/notifications/unified", tags=["notifications-unified"])

# Role yang boleh melihat inbox orang lain / seluruh notifikasi (audit & bantuan).
ADMIN_VIEW_ROLES = set(SUPER_ROLES) | {"hr", "manager_hr", "hr_manager"}


def _assert_may_inspect_others(user: dict, *, what: str):
    role = (user.get("role") or "").lower()
    if role not in ADMIN_VIEW_ROLES:
        raise HTTPException(403, f"Akses ditolak: hanya admin/owner/HR boleh {what}.")


@router.get("")
async def list_unified(
    request: Request,
    type: Optional[str] = Query(None, description=f"Filter by type: {sorted(VALID_TYPES)}"),
    severity: Optional[str] = Query(None, description=f"Filter by severity: {sorted(VALID_SEVERITIES)}"),
    unread_only: bool = Query(False),
    user_id: Optional[str] = Query(None, description="Override recipient. Defaults to current user."),
    all_users: bool = Query(False, description="Admin/HR only: include broadcast notifs"),
    limit: int = Query(50, ge=1, le=200),
    skip: int = Query(0, ge=0),
):
    user = await require_auth(request)
    db = get_db()

    if type and type not in VALID_TYPES:
        raise HTTPException(400, f"invalid type. allowed: {sorted(VALID_TYPES)}")
    if severity and severity not in VALID_SEVERITIES:
        raise HTTPException(400, f"invalid severity. allowed: {sorted(VALID_SEVERITIES)}")

    # RBAC (2026-08-07): sebelumnya SIAPA PUN bisa mengirim `user_id` orang lain
    # atau `all_users=true` dan membaca notifikasi seluruh karyawan. Sekarang
    # hanya admin/owner/HR.
    uid = user.get('id')
    if all_users:
        _assert_may_inspect_others(user, what="melihat notifikasi semua user")
    elif user_id and user_id != uid:
        _assert_may_inspect_others(user, what="melihat notifikasi user lain")

    if all_users or (user_id and user_id != uid):
        from utils.notif_unified import notif_list
        items = await notif_list(
            db, user_id=None if all_users else user_id, type=type, severity=severity,
            unread_only=unread_only, limit=limit, skip=skip)
        effective_uid = None if all_users else user_id
    else:
        # Jalur normal: audiens ditegakkan (personal + target role/user).
        items = await notif_list_for(
            db, user, type=type, severity=severity, unread_only=unread_only,
            limit=limit, skip=skip)
        effective_uid = uid

    return {
        'items': [{**serialize_notif(it),
                   'read': not notif_is_unread_for(it, user)} for it in items],
        'count': len(items),
        'limit': limit,
        'skip':  skip,
        'filter': {
            'type':         type,
            'severity':     severity,
            'unread_only':  unread_only,
            'user_id':      effective_uid,
            'all_users':    all_users,
        },
    }


@router.get("/stats")
async def stats_unified(
    request: Request,
    user_id: Optional[str] = Query(None),
    all_users: bool = Query(False),
):
    user = await require_auth(request)
    db = get_db()
    uid = user.get('id')
    if all_users:
        _assert_may_inspect_others(user, what="melihat statistik notifikasi semua user")
    elif user_id and user_id != uid:
        _assert_may_inspect_others(user, what="melihat statistik notifikasi user lain")

    inspect_other = all_users or (user_id and user_id != uid)
    effective_uid = None if all_users else (user_id or uid)

    by_type: dict = {t: 0 for t in VALID_TYPES}
    by_severity: dict = {s: 0 for s in VALID_SEVERITIES}

    # Jalur normal memakai aturan audiens; jalur admin memakai filter user_id.
    flt: dict = ({'user_id': effective_uid} if effective_uid else {}) if inspect_other \
        else notif_audience_query(user)

    pipeline_type = [
        {'$match': flt},
        {'$group': {'_id': '$type', 'count': {'$sum': 1}}},
    ]
    async for row in db.notifications.aggregate(pipeline_type):
        if row['_id'] in by_type:
            by_type[row['_id']] = row['count']

    pipeline_sev = [
        {'$match': flt},
        {'$group': {'_id': '$severity', 'count': {'$sum': 1}}},
    ]
    async for row in db.notifications.aggregate(pipeline_sev):
        if row['_id'] in by_severity:
            by_severity[row['_id']] = row['count']

    total = await db.notifications.count_documents(flt)
    unread = (await notif_count_unread(db, user_id=effective_uid) if inspect_other
              else await notif_count_unread_for(db, user))

    return {
        'total':       total,
        'unread':      unread,
        'by_type':     by_type,
        'by_severity': by_severity,
    }


@router.post("/{notif_id}/mark-read")
async def mark_read(notif_id: str, request: Request):
    """Tandai dibaca HANYA untuk user ini.

    2026-08-07: dulu notifikasi banyak penerima ditandai `read=True` global,
    sehingga satu orang membaca = dianggap dibaca semua penerima. Sekarang
    dokumen bersama memakai `meta.read_by` per orang, dan user tidak bisa
    menandai notifikasi yang bukan untuknya.
    """
    user = await require_auth(request)
    db = get_db()
    if not await notif_mark_read_for(db, notif_id, user):
        raise HTTPException(404, 'notification not found')
    return {'ok': True}


@router.post("/mark-all-read")
async def mark_all_read(
    request: Request,
    type: Optional[str] = Query(None),
):
    user = await require_auth(request)
    db = get_db()
    modified = await notif_mark_all_read_for(
        db, user, type=type if (type and type in VALID_TYPES) else None)
    return {'ok': True, 'modified': modified}
