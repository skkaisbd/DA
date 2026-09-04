"""
Activity Feed — Portal Kolaborasi
Aggregates recent events from LMS, Workspace, and Communication for a unified activity stream.
Prefix: /api/collab/activity-feed
"""
import logging
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, Query
from database import get_db
from auth import require_auth

router = APIRouter(prefix='/api/collab/activity-feed', tags=['activity-feed'])


def _ser_dt(doc):
    if not doc:
        return None
    doc = dict(doc)
    doc.pop('_id', None)
    for k, v in list(doc.items()):
        if isinstance(v, datetime):
            doc[k] = v.isoformat()
    return doc


@router.get('')
async def get_activity_feed(
    limit: int = Query(30, ge=5, le=100),
    days: int = Query(7, ge=1, le=30),
    db=Depends(get_db),
    user=Depends(require_auth),
):
    """
    Returns aggregated activity feed for the current user.
    Includes: LMS enrollments, completions, submissions; Workspace doc edits; channel messages.
    """
    since = datetime.now(timezone.utc) - timedelta(days=days)
    activities = []

    # --- LMS Enrollments ---
    enrollments = await db.dewi_lms_enrollments.find(
        {'enrolled_at': {'$gte': since}}
    ).sort('enrolled_at', -1).to_list(limit)

    for e in enrollments:
        course = await db.dewi_lms_courses.find_one({'course_id': e.get('course_id')})
        title = course.get('title', 'Course') if course else 'Course'
        activities.append({
            'id': f"enroll-{e.get('enrollment_id', '')}",
            'type': 'course_enroll',
            'icon': '📚',
            'actor': e.get('user_id', ''),
            'actor_name': e.get('user_name', 'Pengguna'),
            'action': 'mendaftar ke course',
            'subject': title,
            'subject_id': e.get('course_id', ''),
            'subject_type': 'course',
            'timestamp': e.get('enrolled_at'),
        })

    # --- LMS Material Completions ---
    completions = await db.dewi_lms_progress.find(
        {'completed_at': {'$gte': since}, 'status': 'completed'}
    ).sort('completed_at', -1).to_list(limit)

    for p in completions:
        mat = await db.dewi_lms_materials.find_one({'material_id': p.get('material_id')})
        mat_title = mat.get('title', 'Materi') if mat else 'Materi'
        mat_type  = mat.get('type', 'materi') if mat else 'materi'
        icon = {
            'video': '🎥', 'text': '📝', 'pdf': '📄',
            'quiz': '❓', 'assignment': '📝',
        }.get(mat_type, '✅')
        activities.append({
            'id': f"complete-{p.get('progress_id', '')}",
            'type': f'material_complete_{mat_type}',
            'icon': icon,
            'actor': p.get('user_id', ''),
            'actor_name': p.get('user_name', 'Pengguna'),
            'action': f'menyelesaikan {mat_type}',
            'subject': mat_title,
            'subject_id': p.get('course_id', ''),
            'subject_type': 'course',
            'timestamp': p.get('completed_at'),
        })

    # --- LMS Assignment Submissions ---
    submissions = await db.dewi_lms_submissions.find(
        {'submitted_at': {'$gte': since}}
    ).sort('submitted_at', -1).to_list(limit)

    for s in submissions:
        mat = await db.dewi_lms_materials.find_one({'material_id': s.get('assignment_id')})
        assign_title = mat.get('title', 'Tugas') if mat else 'Tugas'
        activities.append({
            'id': f"submit-{s.get('submission_id', '')}",
            'type': 'assignment_submit',
            'icon': '📎',
            'actor': s.get('user_id', ''),
            'actor_name': s.get('user_name', 'Pengguna'),
            'action': 'mengumpulkan tugas',
            'subject': assign_title,
            'subject_id': s.get('course_id', ''),
            'subject_type': 'course',
            'timestamp': s.get('submitted_at'),
        })

    # --- Workspace Documents (updated recently) ---
    docs = await db.workspace_documents.find(
        {'owner_id': user['id'], 'updated_at': {'$gte': since}}
    ).sort('updated_at', -1).to_list(10)

    for d in docs:
        activities.append({
            'id': f"doc-{d.get('doc_id', '')}",
            'type': 'document_update',
            'icon': '📄',
            'actor': user['id'],
            'actor_name': user.get('name', 'Anda'),
            'action': 'memperbarui dokumen',
            'subject': d.get('name', 'Dokumen'),
            'subject_id': d.get('doc_id', ''),
            'subject_type': 'document',
            'timestamp': d.get('updated_at'),
        })

    # --- Sort all by timestamp descending ---
    def ts_key(item):
        ts = item.get('timestamp')
        if isinstance(ts, datetime):
            return ts
        if isinstance(ts, str):
            try:
                return datetime.fromisoformat(ts.replace('Z', '+00:00'))
            except Exception:
                logging.getLogger(__name__).debug("suppressed exception", exc_info=True)
        return datetime.min.replace(tzinfo=timezone.utc)

    activities.sort(key=ts_key, reverse=True)
    activities = activities[:limit]

    # Serialize timestamps
    for a in activities:
        if isinstance(a.get('timestamp'), datetime):
            a['timestamp'] = a['timestamp'].isoformat()

    # Get user display names for actor_name enrichment
    actor_ids = list(set(a['actor'] for a in activities if a.get('actor')))
    if actor_ids:
        users_db = await db.users.find({'id': {'$in': actor_ids}}).to_list(100)
        user_map = {u['id']: u.get('name', 'Pengguna') for u in users_db}
        for a in activities:
            if a.get('actor') in user_map and a['actor_name'] in ('Pengguna', ''):
                a['actor_name'] = user_map[a['actor']]

    return {
        'ok': True,
        'activities': activities,
        'total': len(activities),
        'days': days,
    }
