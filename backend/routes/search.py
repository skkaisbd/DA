"""
Universal Search + Link Preview — Portal Kolaborasi
Searches across: channels, messages, documents (Workspace), LMS courses, materials, people.
Also resolves deep links for preview cards in chat.
Prefix: /api/collab/search
"""
import logging
import re
from datetime import datetime
from fastapi import APIRouter, Depends, Query, HTTPException
from database import get_db
from auth import require_auth

router = APIRouter(prefix='/api/collab/search', tags=['universal-search'])


def _ser(doc, keep=None):
    if not doc:
        return None
    doc = dict(doc)
    doc.pop('_id', None)
    for k, v in list(doc.items()):
        if isinstance(v, datetime):
            doc[k] = v.isoformat()
    if keep:
        return {k: doc[k] for k in keep if k in doc}
    return doc


def _regex(q):
    """Case-insensitive regex for partial match."""
    return {'$regex': re.escape(q), '$options': 'i'}


# ── Link Preview ─────────────────────────────────────────────────────────────

@router.get('/link-preview')
async def get_link_preview(
    type: str,
    id: str,
    db=Depends(get_db),
    user=Depends(require_auth),
):
    """Resolve a deep link to its preview data (title, subtitle, etc.)."""
    if type == 'course':
        doc = await db.dewi_lms_courses.find_one({'course_id': id})
        if not doc:
            raise HTTPException(404, 'Course tidak ditemukan')
        return {
            'type': 'course',
            'id': id,
            'title': doc.get('title', 'Course'),
            'subtitle': f"{doc.get('category', '')} • {doc.get('level', '')} • {doc.get('enrollment_count', 0)} peserta",
        }
    elif type == 'doc':
        doc = await db.workspace_documents.find_one({'doc_id': id})
        if not doc:
            raise HTTPException(404, 'Dokumen tidak ditemukan')
        upd = doc.get('updated_at', '')
        if isinstance(upd, datetime):
            upd = upd.isoformat()
        return {
            'type': 'doc',
            'id': id,
            'title': doc.get('name', 'Dokumen'),
            'subtitle': f"Diperbarui: {upd[:10] if upd else ''}",
        }
    elif type == 'channel':
        ch = await db.comm_channels.find_one({'id': id})
        if not ch:
            raise HTTPException(404, 'Channel tidak ditemukan')
        return {
            'type': 'channel',
            'id': id,
            'title': f"#{ch.get('name', 'channel')}",
            'subtitle': ch.get('description', ''),
        }
    raise HTTPException(400, 'Tipe link tidak valid')


# ── Universal Search ──────────────────────────────────────────────────────────

@router.get('')
async def universal_search(
    q: str = Query(..., min_length=1),
    limit: int = Query(5, ge=1, le=20),
    db=Depends(get_db),
    user=Depends(require_auth),
):
    """Search across channels, courses, documents, and people."""
    results = {
        'channels': [],
        'courses': [],
        'documents': [],
        'people': [],
        'messages': [],
        'materials': [],
        'total': 0,
    }

    # 1. Channels
    channels = await db.comm_channels.find(
        {'name': _regex(q), 'archived': {'$ne': True}}
    ).to_list(limit)
    results['channels'] = [
        _ser(c, ['id', 'name', 'type', 'description', 'member_count'])
        for c in channels
    ]

    # 2. LMS Courses
    courses = await db.dewi_lms_courses.find(
        {'$or': [
            {'title': _regex(q)},
            {'description': _regex(q)},
            {'category': _regex(q)},
        ]}
    ).to_list(limit)
    results['courses'] = [
        _ser(c, ['course_id', 'title', 'description', 'category', 'level', 'enrollment_count'])
        for c in courses
    ]

    # 3. LMS Materials
    materials = await db.dewi_lms_materials.find(
        {'title': _regex(q)}
    ).to_list(limit)
    results['materials'] = [
        _ser(m, ['material_id', 'course_id', 'title', 'type', 'description'])
        for m in materials
    ]

    # 4. Workspace Documents
    docs = await db.workspace_documents.find(
        {'owner_id': user['id'], 'name': _regex(q)}
    ).to_list(limit)
    results['documents'] = [
        _ser(d, ['doc_id', 'name', 'type', 'created_at', 'updated_at'])
        for d in docs
    ]

    # 5. Messages (in channels user is a member of)
    try:
        member_channels = await db.comm_channels.find(
            {'members': user['id']}
        ).to_list(200)
        member_channel_ids = [c['id'] for c in member_channels]
        if member_channel_ids:
            messages = await db.comm_messages.find(
                {'channel_id': {'$in': member_channel_ids}, 'content': _regex(q), 'deleted': {'$ne': True}}
            ).sort('created_at', -1).to_list(limit)
            results['messages'] = [
                _ser(m, ['id', 'channel_id', 'content', 'sender_name', 'created_at'])
                for m in messages
            ]
    except Exception:
        logging.getLogger(__name__).debug("suppressed exception", exc_info=True)

    # 6. People (users)
    people = await db.users.find(
        {'$or': [
            {'name': _regex(q)},
            {'email': _regex(q)},
            {'department': _regex(q)},
        ]}
    ).to_list(limit)
    results['people'] = [
        _ser(p, ['id', 'name', 'email', 'role', 'department', 'position'])
        for p in people
    ]

    results['total'] = sum(
        len(results[k])
        for k in ['channels', 'courses', 'documents', 'people', 'messages', 'materials']
    )
    results['query'] = q

    return results
