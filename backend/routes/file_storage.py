"""File upload/download routes with persistent storage."""
from fastapi import APIRouter, Request, HTTPException, UploadFile, File, Query
from fastapi.responses import Response
from database import get_db
from auth import require_auth, serialize_doc
from storage import put_object, get_object, generate_storage_path
import uuid
from datetime import datetime, timezone
import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api")

def new_id(): return str(uuid.uuid4())
def now(): return datetime.now(timezone.utc)

@router.post("/upload")
async def upload_file(request: Request, file: UploadFile = File(...),
                      entity_type: str = Query(''), entity_id: str = Query('')):
    user = await require_auth(request)
    db = get_db()
    data = await file.read()
    if len(data) > 10 * 1024 * 1024:  # 10MB limit
        raise HTTPException(400, 'File terlalu besar (max 10MB)')
    try:
        path = generate_storage_path(user['id'], file.filename)
        result = put_object(path, data, file.content_type or 'application/octet-stream')
        file_doc = {
            'id': new_id(), 'storage_path': result.get('path', path),
            'original_filename': file.filename, 'content_type': file.content_type,
            'size': result.get('size', len(data)),
            'entity_type': entity_type, 'entity_id': entity_id,
            'uploaded_by': user.get('name', ''), 'uploaded_by_id': user['id'],
            'is_deleted': False, 'created_at': now()
        }
        await db.attachments.insert_one(file_doc)
        return serialize_doc(file_doc)
    except RuntimeError:
        # Storage not available, save metadata only
        file_doc = {
            'id': new_id(), 'storage_path': '', 'original_filename': file.filename,
            'content_type': file.content_type, 'size': len(data),
            'entity_type': entity_type, 'entity_id': entity_id,
            'uploaded_by': user.get('name', ''), 'uploaded_by_id': user['id'],
            'is_deleted': False, 'created_at': now()
        }
        await db.attachments.insert_one(file_doc)
        return serialize_doc(file_doc)
    except Exception as e:
        logger.error(f"Upload error: {e}")
        raise HTTPException(500, f"Upload failed: {str(e)}")

@router.get("/files/{path:path}")
async def download_file(path: str, request: Request, auth: str = Query(None)):
    """Ambil berkas berdasarkan storage path. Mendukung `?auth=token` untuk <img src>.

    2026-08-07 — KEAMANAN: sebelumnya token di-decode dengan
    `verify_signature=False`, sehingga siapa pun bisa membuat JWT palsu dan
    mengunduh berkas (foto karyawan, dokumen HR, lampiran RnD). Sekarang tanda
    tangan diverifikasi lewat `auth.verify_token_str` — satu jalur dengan
    `require_auth`. Query-param tetap didukung karena tag <img> browser tidak
    bisa mengirim header Authorization.
    """
    from auth import verify_token_str
    header = request.headers.get('Authorization', '')
    raw = header.split(' ', 1)[1].strip() if header.startswith('Bearer ') else (auth or '')
    if not raw or not verify_token_str(raw):
        raise HTTPException(401, 'Unauthorized')
    db = get_db()
    record = await db.attachments.find_one({'storage_path': path, 'is_deleted': False})
    if not record:
        raise HTTPException(404, 'File not found')
    try:
        data, content_type = get_object(path)
        return Response(content=data, media_type=record.get('content_type', content_type))
    except Exception as e:
        raise HTTPException(500, f"Download failed: {str(e)}")

@router.delete("/attachments/{att_id}")
async def delete_attachment(att_id: str, request: Request):
    await require_auth(request)
    db = get_db()
    doc = await db.attachments.find_one({'id': att_id})
    if not doc:
        raise HTTPException(404, 'Not found')
    # Soft delete
    await db.attachments.update_one({'id': att_id}, {'$set': {'is_deleted': True, 'deleted_at': now()}})
    return {'success': True}


@router.put("/attachments/{att_id}/meta")
async def update_attachment_meta(att_id: str, request: Request):
    """Update metadata (e.g. category label) for an attachment."""
    await require_auth(request)
    db = get_db()
    body = await request.json()
    upd = {}
    for k in ('category', 'description', 'entity_type', 'entity_id'):
        if k in body:
            upd[k] = body[k]
    upd['updated_at'] = now()
    res = await db.attachments.update_one({'id': att_id}, {'$set': upd})
    if res.matched_count == 0:
        raise HTTPException(404, 'Not found')
    return {'success': True}
