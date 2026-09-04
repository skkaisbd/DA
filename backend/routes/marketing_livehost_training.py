# ruff: noqa: F401
"""
marketing_livehost_training.py — Training & Certification Management
Extracted from marketing_livehost.py (2278 LOC monolith)

Refactored: Session #11.19 Phase 3.2 Batch #2
Endpoints: POST /training, GET /training, PUT /training/{id}, DELETE /training/{id}, POST /training/assign, GET /training/progress, POST /training/progress/{id}/complete
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

router = APIRouter(prefix='/api/marketing/livehost', tags=['Marketing-LiveHost-Training'])

@router.post('/training')
async def create_training(data: TrainingCreate, request: Request):
    """Admin creates a training module"""
    await require_auth(request)
    db = get_db()
    
    training = {
        'id': _uid(),
        'title': data.title,
        'category': data.category,
        'description': data.description,
        'content_type': data.content_type,
        'content_url': data.content_url or '',
        'duration_minutes': data.duration_minutes,
        'is_required': data.is_required,
        'expiry_months': data.expiry_months,
        'passing_score': data.passing_score,
        'is_active': True,
        'created_at': _now(),
        'created_by': _get_user(request).get('email', 'system'),
    }
    
    await db.marketing_livehost_training.insert_one(training)
    
    user = _get_user(request)
    await log_activity(
        user.get('id', 'system'),
        user.get('name') or user.get('email', 'system'),
        'create', 'marketing_livehost_training',
        f"Created training: {data.title}"
    )
    
    return serialize_doc({'message': 'Training berhasil dibuat', 'training': training})


@router.get('/training')
async def list_training(
    request: Request,
    category: Optional[str] = Query(None),
    is_required: Optional[bool] = Query(None),
):
    """Admin lists all training modules"""
    await require_auth(request)
    db = get_db()
    
    query = {'is_active': True}
    if category:
        query['category'] = category
    if is_required is not None:
        query['is_required'] = is_required
    
    trainings = await db.marketing_livehost_training.find(
        query, {'_id': 0}
    ).sort('created_at', -1).to_list(500)
    
    return serialize_doc(trainings)


@router.put('/training/{training_id}')
async def update_training(training_id: str, data: TrainingCreate, request: Request):
    """Admin updates training module"""
    await require_auth(request)
    db = get_db()
    
    training = await db.marketing_livehost_training.find_one({'id': training_id}, {'_id': 0})
    if not training:
        raise HTTPException(404, 'Training tidak ditemukan')
    
    update_data = {
        'title': data.title,
        'category': data.category,
        'description': data.description,
        'content_type': data.content_type,
        'content_url': data.content_url or training.get('content_url', ''),
        'duration_minutes': data.duration_minutes,
        'is_required': data.is_required,
        'expiry_months': data.expiry_months,
        'passing_score': data.passing_score,
        'updated_at': _now(),
    }
    
    await db.marketing_livehost_training.update_one({'id': training_id}, {'$set': update_data})
    
    return serialize_doc({'message': 'Training berhasil diupdate'})


@router.delete('/training/{training_id}')
async def delete_training(training_id: str, request: Request):
    """Admin deletes training (soft delete)"""
    await require_auth(request)
    db = get_db()
    
    training = await db.marketing_livehost_training.find_one({'id': training_id}, {'_id': 0})
    if not training:
        raise HTTPException(404, 'Training tidak ditemukan')
    
    await db.marketing_livehost_training.update_one(
        {'id': training_id},
        {'$set': {'is_active': False, 'updated_at': _now()}}
    )
    
    return serialize_doc({'message': 'Training berhasil dihapus'})


# ══════════════════════════════════════════════════════════════════════════════
# TRAINING ASSIGNMENT & PROGRESS
# ══════════════════════════════════════════════════════════════════════════════

@router.post('/training/assign')
async def assign_training(data: TrainingAssign, request: Request):
    """Admin assigns training to LiveHosts"""
    await require_auth(request)
    db = get_db()
    
    # Validate training exists
    training = await db.marketing_livehost_training.find_one({'id': data.training_id}, {'_id': 0})
    if not training:
        raise HTTPException(404, 'Training tidak ditemukan')
    
    # Validate hosts exist
    hosts = await db.marketing_livehosts.find(
        {'id': {'$in': data.host_ids}}, {'_id': 0, 'id': 1, 'name': 1}
    ).to_list(500)
    
    if len(hosts) != len(data.host_ids):
        raise HTTPException(400, 'Beberapa LiveHost tidak ditemukan')
    
    # Calculate expiry date if training has expiry
    expiry_date = None
    if training.get('expiry_months'):
        from dateutil.relativedelta import relativedelta
        expiry_date = _now() + relativedelta(months=training['expiry_months'])
    
    # Create progress records for each host
    assignments = []
    for host in hosts:
        # Check if already assigned
        existing = await db.marketing_livehost_training_progress.find_one({
            'host_id': host['id'],
            'training_id': data.training_id,
        })
        
        if existing:
            continue  # Skip if already assigned
        
        progress = {
            'id': _uid(),
            'host_id': host['id'],
            'host_name': host['name'],
            'training_id': data.training_id,
            'training_title': training['title'],
            'status': 'not_started',  # not_started | in_progress | completed
            'score': None,
            'started_at': None,
            'completed_at': None,
            'expiry_date': expiry_date,
            'certificate_url': None,
            'assigned_at': _now(),
            'assigned_by': _get_user(request).get('email', 'system'),
        }
        
        await db.marketing_livehost_training_progress.insert_one(progress)
        assignments.append(progress)

        # SSE: notify host about new training assignment
        try:
            await publish_livehost_notification(
                db,
                host_id=host['id'],
                type_='training_assigned',
                severity='info',
                title='Training Baru di-Assign',
                message=f"Anda di-assign training: {training['title']}",
                link='/training',
            )
        except Exception:
            logging.getLogger(__name__).debug("suppressed exception", exc_info=True)
    
    user = _get_user(request)
    await log_activity(
        user.get('id', 'system'),
        user.get('name') or user.get('email', 'system'),
        'create', 'marketing_livehost_training_assignment',
        f"Assigned training '{training['title']}' to {len(assignments)} LiveHost(s)"
    )
    
    return serialize_doc({
        'message': f'Training berhasil di-assign ke {len(assignments)} LiveHost',
        'assignments': len(assignments),
        'skipped': len(data.host_ids) - len(assignments),
    })


@router.get('/training/progress')
async def get_training_progress(
    request: Request,
    host_id: Optional[str] = Query(None),
    training_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
):
    """Admin views training progress"""
    await require_auth(request)
    db = get_db()
    
    query = {}
    if host_id:
        query['host_id'] = host_id
    if training_id:
        query['training_id'] = training_id
    if status:
        query['status'] = status
    
    progress_list = await db.marketing_livehost_training_progress.find(
        query, {'_id': 0}
    ).sort('assigned_at', -1).to_list(500)
    
    return serialize_doc(progress_list)


@router.post('/training/progress/{progress_id}/complete')
async def complete_training(progress_id: str, data: TrainingComplete, request: Request):
    """Admin marks training as completed for a LiveHost"""
    await require_auth(request)
    db = get_db()
    
    progress = await db.marketing_livehost_training_progress.find_one({'id': progress_id}, {'_id': 0})
    if not progress:
        raise HTTPException(404, 'Training progress tidak ditemukan')
    
    if progress['status'] == 'completed':
        raise HTTPException(400, 'Training sudah completed sebelumnya')
    
    # Get training details for validation
    training = await db.marketing_livehost_training.find_one({'id': progress['training_id']}, {'_id': 0})
    if not training:
        raise HTTPException(404, 'Training tidak ditemukan')
    
    # Validate passing score if quiz type
    if training.get('passing_score') and data.score is not None:
        if data.score < training['passing_score']:
            raise HTTPException(400, f"Score {data.score} tidak mencapai passing score {training['passing_score']}")
    
    # Calculate new expiry date
    expiry_date = None
    if training.get('expiry_months'):
        from dateutil.relativedelta import relativedelta
        expiry_date = _now() + relativedelta(months=training['expiry_months'])
    
    update_data = {
        'status': 'completed',
        'score': data.score,
        'completed_at': _now(),
        'expiry_date': expiry_date,
    }
    
    await db.marketing_livehost_training_progress.update_one({'id': progress_id}, {'$set': update_data})
    
    # Update host's training_completed list
    await db.marketing_livehosts.update_one(
        {'id': progress['host_id']},
        {'$addToSet': {'training_completed': progress['training_id']}}
    )
    
    return serialize_doc({'message': 'Training berhasil di-mark as completed'})


# ══════════════════════════════════════════════════════════════════════════════
# PHASE 3: ANALYTICS & PAYMENT CALCULATION
# ══════════════════════════════════════════════════════════════════════════════

