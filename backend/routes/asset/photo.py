"""Asset photo upload: POST /{asset_id}/upload-photo (multipart)."""
from fastapi import Request, HTTPException, UploadFile, File

from database import get_db
from auth import require_auth
from storage import put_object, generate_storage_path
from ._helpers import router, _now


@router.post("/{asset_id}/upload-photo")
async def upload_asset_photo(asset_id: str, request: Request, file: UploadFile = File(...)):
    """Upload foto asset untuk visual identification (max 5 MB, image/*)."""
    await require_auth(request)
    db = get_db()

    asset = await db.dewi_assets.find_one({"id": asset_id}, {"_id": 0, "asset_number": 1})
    if not asset:
        raise HTTPException(404, "Aset tidak ditemukan.")

    if file.content_type and not file.content_type.startswith("image/"):
        raise HTTPException(400, "File harus berupa gambar (jpg, png, etc)")

    if file.size and file.size > 5 * 1024 * 1024:
        raise HTTPException(400, "Ukuran foto maksimal 5 MB")

    content_bytes = await file.read()
    storage_path = generate_storage_path(f"assets/{asset_id}", file.filename)
    stored = put_object(storage_path, content_bytes, file.content_type or "image/jpeg")
    photo_url = stored["url"]

    await db.dewi_assets.update_one(
        {"id": asset_id},
        {"$set": {"photo_url": photo_url, "updated_at": _now()}},
    )

    return {"ok": True, "photo_url": photo_url}
