"""
CV. Dewi Aditya — Phase 4: Client Portal — Admin provisioning endpoints
Internal-only routes (require_auth) used by Maklon admins to create / reset
client portal accounts.

Endpoints under: /api/dewi/maklon/clients/{client_id}/portal-*
"""
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field, EmailStr
from typing import Optional
from datetime import datetime, timezone
from database import get_db
from auth import require_auth, hash_password, generate_password
import uuid

router = APIRouter(prefix='/api/dewi/maklon/clients', tags=['Dewi-Maklon-Client-Admin'])


def _clean(doc):
    if not doc:
        return doc
    doc.pop('_id', None)
    doc.pop('password', None)
    return doc


class ProvisionIn(BaseModel):
    email: EmailStr
    name: Optional[str] = None  # contact person name
    password: Optional[str] = Field(default=None, description="Optional, otherwise auto-generated")


class ResetPasswordIn(BaseModel):
    new_password: Optional[str] = None  # optional, otherwise auto-generated


@router.get('/{client_id}/portal-status')
async def portal_status(client_id: str, user: dict = Depends(require_auth)):
    db = get_db()
    cl = await db.dewi_maklon_clients.find_one({'id': client_id})
    if not cl:
        raise HTTPException(404, 'Client tidak ditemukan')
    accounts = await db.dewi_client_users.find({'client_id': client_id}).to_list(length=20)
    return {
        'client_id': client_id,
        'has_account': len(accounts) > 0,
        'accounts': [_clean(a) for a in accounts],
    }


@router.post('/{client_id}/provision-portal')
async def provision_portal(
    client_id: str,
    payload: ProvisionIn,
    user: dict = Depends(require_auth),
):
    db = get_db()
    cl = await db.dewi_maklon_clients.find_one({'id': client_id})
    if not cl:
        raise HTTPException(404, 'Client tidak ditemukan')

    email = payload.email.lower().strip()
    existing = await db.dewi_client_users.find_one({'email': email})
    if existing:
        raise HTTPException(400, f'Email {email} sudah terdaftar')

    raw_pw = payload.password or generate_password(10)
    now = datetime.now(timezone.utc)
    doc = {
        'id': str(uuid.uuid4()),
        'email': email,
        'name': payload.name or cl.get('pic_name') or cl.get('name'),
        'password': hash_password(raw_pw),
        'must_change_password': True,
        'client_id': client_id,
        'client_name': cl.get('name'),
        'role': 'maklon_client',
        'status': 'active',
        'created_at': now,
        'updated_at': now,
        'created_by': user.get('name', 'System'),
        'last_login_at': None,
    }
    await db.dewi_client_users.insert_one(doc)
    return {
        'message': 'Akun portal klien berhasil dibuat',
        'email': email,
        'password': raw_pw,  # one-time return; admin must save/share securely
        'must_change_password': True,
    }


@router.post('/{client_id}/portal-accounts/{account_id}/reset-password')
async def reset_portal_password(
    client_id: str,
    account_id: str,
    payload: ResetPasswordIn,
    user: dict = Depends(require_auth),
):
    db = get_db()
    acc = await db.dewi_client_users.find_one({'id': account_id, 'client_id': client_id})
    if not acc:
        raise HTTPException(404, 'Akun portal tidak ditemukan')
    raw_pw = payload.new_password or generate_password(10)
    await db.dewi_client_users.update_one(
        {'id': account_id},
        {'$set': {
            'password': hash_password(raw_pw),
            'must_change_password': True,
            'updated_at': datetime.now(timezone.utc),
        }},
    )
    return {
        'message': 'Password direset',
        'email': acc.get('email'),
        'password': raw_pw,
    }


@router.post('/{client_id}/portal-accounts/{account_id}/toggle')
async def toggle_portal_account(
    client_id: str,
    account_id: str,
    user: dict = Depends(require_auth),
):
    db = get_db()
    acc = await db.dewi_client_users.find_one({'id': account_id, 'client_id': client_id})
    if not acc:
        raise HTTPException(404, 'Akun portal tidak ditemukan')
    new_status = 'inactive' if acc.get('status') == 'active' else 'active'
    await db.dewi_client_users.update_one(
        {'id': account_id},
        {'$set': {'status': new_status, 'updated_at': datetime.now(timezone.utc)}},
    )
    return {'message': f'Status akun → {new_status}', 'status': new_status}


@router.delete('/{client_id}/portal-accounts/{account_id}')
async def delete_portal_account(
    client_id: str,
    account_id: str,
    user: dict = Depends(require_auth),
):
    db = get_db()
    res = await db.dewi_client_users.delete_one({'id': account_id, 'client_id': client_id})
    if res.deleted_count == 0:
        raise HTTPException(404, 'Akun portal tidak ditemukan')
    return {'message': 'Akun portal dihapus'}
