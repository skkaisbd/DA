"""
Notifications — Portal Kolaborasi
Unified in-app notification system: chat mentions, LMS events, document sharing.
Collection: notifications SSOT (type='collab')

P3 TD-010 Phase B (Session #11.12): writes now go to the unified SSOT
`notifications` collection with `type='collab'`. Public API surface
(endpoints, request/response shape) preserved via reshape helpers.
"""
import logging
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, Query, HTTPException
from pydantic import BaseModel
from typing import Optional
from database import get_db
from auth import require_auth
from utils.notif_unified import (
    notif_insert,
    reshape_as_collab,
)

logger = logging.getLogger(__name__)
logger.info(
    "[NOTIF-CONSOLIDATION] collab_notifications router now writes/reads SSOT "
    "(collection: notifications, type='collab')."
)

router = APIRouter(prefix='/api/collab/notifications', tags=['notifications'])

NOTIF_TYPES = [
    'message',       # New message in channel you're in
    'mention',       # @mention in message
    'document',      # Document shared with you / comment
    'course',        # New course assigned / enrolled
    'assignment',    # Assignment graded / deadline
    'grade',         # Quiz / assignment graded
    'certificate',   # Certificate earned
    'deadline',      # Approaching deadline
    'system',        # System announcement
]

TYPE_ICONS = {
    'message':     '💬',
    'mention':     '@',
    'document':    '📄',
    'course':      '📚',
    'assignment':  '📝',
    'grade':       '⭐',
    'certificate': '🎓',
    'deadline':    '⏰',
    'system':      '🔔',
}


async def create_notification(
    db,
    user_id: str,
    notif_type: str,
    title: str,
    content: str,
    source_type: str = 'system',
    source_id: str = '',
    source_url: str = '',
    metadata: dict = None,
):
    """Helper called by other route modules to create a notification."""
    nid = str(uuid.uuid4())
    meta = dict(metadata or {})
    meta['icon'] = TYPE_ICONS.get(notif_type, '🔔')
    await notif_insert(
        db,
        id=nid,
        type='collab',
        body=content,
        subtype=notif_type,
        title=title,
        user_id=user_id,
        source_type=source_type,
        source_id=source_id,
        source_url=source_url,
        meta=meta,
    )
    # Return a doc in legacy shape (frontend compatible)
    return {
        'notification_id': nid,
        'user_id':         user_id,
        'type':            notif_type,
        'icon':            meta['icon'],
        'title':           title,
        'content':         content,
        'source_type':     source_type,
        'source_id':       source_id,
        'source_url':      source_url,
        'metadata':        metadata or {},
        'read':            False,
        'read_at':         None,
        'created_at':      datetime.now(timezone.utc).isoformat(),
    }


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.get('')
async def list_notifications(
    limit: int = Query(30, ge=1, le=100),
    unread_only: bool = Query(False),
    db=Depends(get_db),
    user=Depends(require_auth),
):
    """List notifications for current user."""
    filt = {'type': 'collab', 'user_id': user['id']}
    if unread_only:
        filt['read'] = False

    cursor = db.notifications.find(filt, {'_id': 0}).sort('created_at', -1).limit(limit)
    notifications = [reshape_as_collab(n) async for n in cursor]

    unread_count = await db.notifications.count_documents(
        {'type': 'collab', 'user_id': user['id'], 'read': False},
    )

    return {
        'ok': True,
        'notifications': notifications,
        'unread_count': unread_count,
        'total': len(notifications),
    }


@router.get('/unread-count')
async def get_unread_count(
    db=Depends(get_db),
    user=Depends(require_auth),
):
    """Quick unread count for polling."""
    count = await db.notifications.count_documents(
        {'type': 'collab', 'user_id': user['id'], 'read': False},
    )
    return {'ok': True, 'unread_count': count}


@router.post('/{notification_id}/read')
async def mark_notification_read(
    notification_id: str,
    db=Depends(get_db),
    user=Depends(require_auth),
):
    """Mark a single notification as read."""
    result = await db.notifications.update_one(
        {'id': notification_id, 'type': 'collab', 'user_id': user['id']},
        {'$set': {'read': True, 'read_at': datetime.now(timezone.utc)}},
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail='Notifikasi tidak ditemukan')
    return {'ok': True}


@router.post('/mark-all-read')
async def mark_all_read(
    db=Depends(get_db),
    user=Depends(require_auth),
):
    """Mark all notifications as read."""
    now = datetime.now(timezone.utc)
    result = await db.notifications.update_many(
        {'type': 'collab', 'user_id': user['id'], 'read': False},
        {'$set': {'read': True, 'read_at': now}},
    )
    return {'ok': True, 'updated': result.modified_count}


class CreateNotifRequest(BaseModel):
    notif_type: str = 'system'
    title: str
    content: str
    source_type: str = 'system'
    source_id: str = ''
    source_url: str = ''
    target_user_id: Optional[str] = None
    metadata: dict = {}


@router.post('')
async def create_notification_api(
    body: CreateNotifRequest,
    db=Depends(get_db),
    user=Depends(require_auth),
):
    """Create a notification (admin/system use). Target = self if not specified."""
    target = body.target_user_id or user['id']
    doc = await create_notification(
        db,
        user_id=target,
        notif_type=body.notif_type,
        title=body.title,
        content=body.content,
        source_type=body.source_type,
        source_id=body.source_id,
        source_url=body.source_url,
        metadata=body.metadata,
    )
    return {'ok': True, 'notification': doc}


@router.delete('/{notification_id}')
async def delete_notification(
    notification_id: str,
    db=Depends(get_db),
    user=Depends(require_auth),
):
    """Delete a single notification."""
    await db.notifications.delete_one(
        {'id': notification_id, 'type': 'collab', 'user_id': user['id']}
    )
    return {'ok': True}
