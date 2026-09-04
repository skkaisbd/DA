"""
Phase 4 P1: Lightweight file upload endpoint for client portal photo attachments.
Stores files on local filesystem (/app/uploads/client/<client_id>/<uuid>.<ext>).
Returns relative URL that frontend can render via <img src=...>.

Files served via FastAPI's StaticFiles mount (registered in server.py).

Limits:
- Max size: 5MB
- Allowed types: image/jpeg, image/png, image/webp
- Per-client subfolder for soft isolation
"""
import re
import uuid
from fastapi import APIRouter, UploadFile, File, HTTPException, Depends
from routes.dewi_client_portal import require_client_auth
from object_storage import put_object

MAX_BYTES = 5 * 1024 * 1024  # 5MB
ALLOWED_MIMES = {'image/jpeg', 'image/png', 'image/webp'}
ALLOWED_EXT = {'jpg', 'jpeg', 'png', 'webp'}

router = APIRouter(prefix='/api/dewi/client-portal/uploads', tags=['Dewi-Client-Uploads'])


def _safe_ext(filename: str) -> str:
    if not filename or '.' not in filename:
        return 'jpg'
    ext = filename.rsplit('.', 1)[-1].lower()
    ext = re.sub(r'[^a-z0-9]', '', ext)
    return ext if ext in ALLOWED_EXT else 'jpg'


@router.post('')
async def upload_photo(
    file: UploadFile = File(...),
    client: dict = Depends(require_client_auth),
):
    if file.content_type not in ALLOWED_MIMES:
        raise HTTPException(415, f'Tipe file tidak didukung. Hanya {sorted(ALLOWED_MIMES)} diizinkan.')

    data = await file.read()
    if len(data) > MAX_BYTES:
        raise HTTPException(413, f'Ukuran file melebihi {MAX_BYTES // (1024*1024)}MB')
    if len(data) < 100:
        raise HTTPException(400, 'File terlalu kecil / tidak valid')

    cid = client.get('client_id')
    if not cid:
        raise HTTPException(400, 'Client ID tidak ditemukan')

    ext = _safe_ext(file.filename)
    fid = uuid.uuid4().hex
    fname = f'{fid}.{ext}'
    try:
        stored = put_object(f'client/{cid}/{fname}', data, file.content_type)
    except Exception as e:
        raise HTTPException(503, f'Penyimpanan berkas tidak tersedia: {e}')

    url = stored['url']
    return {
        'url': url,
        'filename': fname,
        'size': len(data),
        'content_type': file.content_type,
    }
