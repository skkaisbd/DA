# ruff: noqa: F401
"""
marketing_livehost_scripts.py — Script Library Management
Extracted from marketing_livehost.py (2278 LOC monolith)

Refactored: Session #11.19 Phase 3.2 Batch #2
Endpoints: POST /scripts, GET /scripts, GET /scripts/{id}, PUT /scripts/{id}, DELETE /scripts/{id}
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
    _notif_insert_ssot, _reshape_lh_notif
)
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, List
import json
import asyncio

_log = logging.getLogger(__name__)

router = APIRouter(prefix='/api/marketing/livehost', tags=['Marketing-LiveHost-Scripts'])

@router.post('/scripts')
async def create_script(data: ScriptCreate, request: Request):
    """Admin creates a script"""
    await require_auth(request)
    db = get_db()
    
    script = {
        'id': _uid(),
        'title': data.title,
        'category': data.category,
        'account_id': data.account_id,
        'script_text': data.script_text,
        'language': data.language,
        'products_applicable': data.products_applicable or [],
        'is_active': True,
        'created_at': _now(),
        'created_by': _get_user(request).get('email', 'system'),
    }
    
    await db.marketing_livehost_scripts.insert_one(script)
    
    user = _get_user(request)
    await log_activity(
        user.get('id', 'system'),
        user.get('name') or user.get('email', 'system'),
        'create', 'marketing_livehost_script',
        f"Created script: {data.title}"
    )
    
    return serialize_doc({'message': 'Script berhasil dibuat', 'script': script})


@router.get('/scripts')
async def list_scripts(
    request: Request,
    category: Optional[str] = Query(None),
    account_id: Optional[str] = Query(None),
    language: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
):
    """Admin lists all scripts"""
    await require_auth(request)
    db = get_db()
    
    query = {'is_active': True}
    if category:
        query['category'] = category
    if account_id:
        query['account_id'] = account_id
    if language:
        query['language'] = language
    if search:
        query['$or'] = [
            {'title': {'$regex': search, '$options': 'i'}},
            {'script_text': {'$regex': search, '$options': 'i'}},
        ]
    
    scripts = await db.marketing_livehost_scripts.find(
        query, {'_id': 0}
    ).sort('created_at', -1).to_list(500)
    
    # Enrich dengan account name
    if scripts:
        account_ids = list(set(s['account_id'] for s in scripts if s.get('account_id')))
        if account_ids:
            accounts = await db.marketing_platform_accounts.find(
                {'id': {'$in': account_ids}}, {'_id': 0, 'id': 1, 'account_name': 1}
            ).to_list(500)
            account_map = {a['id']: a['account_name'] for a in accounts}
            for script in scripts:
                if script.get('account_id'):
                    script['account_name'] = account_map.get(script['account_id'], 'Unknown')
                else:
                    script['account_name'] = 'Global (All Accounts)'
    
    return serialize_doc(scripts)


@router.get('/scripts/{script_id}')
async def get_script(script_id: str, request: Request):
    """Admin gets script detail"""
    await require_auth(request)
    db = get_db()
    
    script = await db.marketing_livehost_scripts.find_one({'id': script_id}, {'_id': 0})
    if not script:
        raise HTTPException(404, 'Script tidak ditemukan')
    
    return serialize_doc(script)


@router.put('/scripts/{script_id}')
async def update_script(script_id: str, data: ScriptCreate, request: Request):
    """Admin updates script"""
    await require_auth(request)
    db = get_db()
    
    script = await db.marketing_livehost_scripts.find_one({'id': script_id}, {'_id': 0})
    if not script:
        raise HTTPException(404, 'Script tidak ditemukan')
    
    update_data = {
        'title': data.title,
        'category': data.category,
        'account_id': data.account_id,
        'script_text': data.script_text,
        'language': data.language,
        'products_applicable': data.products_applicable or [],
        'updated_at': _now(),
    }
    
    await db.marketing_livehost_scripts.update_one({'id': script_id}, {'$set': update_data})
    
    user = _get_user(request)
    await log_activity(
        user.get('id', 'system'),
        user.get('name') or user.get('email', 'system'),
        'update', 'marketing_livehost_script',
        f"Updated script: {data.title}"
    )
    
    return serialize_doc({'message': 'Script berhasil diupdate'})


@router.delete('/scripts/{script_id}')
async def delete_script(script_id: str, request: Request):
    """Admin deletes script (soft delete)"""
    await require_auth(request)
    db = get_db()
    
    script = await db.marketing_livehost_scripts.find_one({'id': script_id}, {'_id': 0})
    if not script:
        raise HTTPException(404, 'Script tidak ditemukan')
    
    await db.marketing_livehost_scripts.update_one(
        {'id': script_id},
        {'$set': {'is_active': False, 'updated_at': _now()}}
    )
    
    return serialize_doc({'message': 'Script berhasil dihapus'})


# ══════════════════════════════════════════════════════════════════════════════
# TRAINING MODULES
# ══════════════════════════════════════════════════════════════════════════════

