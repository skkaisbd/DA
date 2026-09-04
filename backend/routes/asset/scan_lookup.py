"""/api/assets/scan-by-number/{asset_number} — LITERAL path lookup (must precede /{asset_id})."""
import re

from fastapi import Request, HTTPException

from database import get_db
from auth import require_auth
from ._helpers import router, _ser


@router.get("/scan-by-number/{asset_number}")
async def get_asset_by_number(asset_number: str, request: Request):
    """Resolve asset by asset_number (untuk scanner apps).

    FASE 20 — `asset_number` DULU disisipkan mentah ke dalam `$regex`. Payload
    hasil scan tak bisa dipercaya bentuknya: barcode/QR rusak atau ketikan manual
    seperti `AST-001(` menghasilkan regex TIDAK VALID → PyMongo melempar error →
    HTTP 500 di jalur yang seharusnya cuma "tidak ditemukan" (404). Karena itu
    pola dikutip dengan `re.escape`, dan pencocokan tetap case-insensitive
    (label dicetak huruf besar, pemindai kadang mengirim huruf kecil).
    """
    code = (asset_number or "").strip()
    if not code:
        raise HTTPException(400, "Nomor aset kosong.")
    await require_auth(request)
    db = get_db()
    asset = await db.dewi_assets.find_one(
        {"asset_number": {"$regex": f"^{re.escape(code)}$", "$options": "i"}},
        {"_id": 0},
    )
    if not asset:
        raise HTTPException(404, f"Aset dengan nomor '{code}' tidak ditemukan.")
    return _ser(asset)
