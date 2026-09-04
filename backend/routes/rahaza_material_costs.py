"""routes/rahaza_material_costs.py — RIWAYAT HARGA BARANG (sesi #33).

Kenapa router terpisah (bukan menambah `/materials/...`): berkas
`rahaza_inventory_materials.py` punya kontrak URUTAN ROUTE yang dijaga gate
INV-F24 (`GET /materials/{id}` WAJIB route terakhir, karena
`/materials/reorder-alerts` & `/materials/uom-options` adalah route LITERAL di
berkas yang sama). Menambah route literal baru di sana = mengundang cacat
urutan. Jadi riwayat harga memakai prefix sendiri: `/api/rahaza/material-costs`.

Endpoint:
  GET /api/rahaza/material-costs/history    — riwayat + ringkasan + ALASAN bila kosong
  GET /api/rahaza/material-costs/materials  — pemilih barang + berapa kali harganya berubah
"""
from fastapi import APIRouter, HTTPException, Query, Request

from auth import require_auth, serialize_doc
from core import material_cost_history as mch
from database import get_db

router = APIRouter(prefix="/api/rahaza/material-costs", tags=["rahaza-material-costs"])


def _types(type_param: str) -> list | None:
    t = (type_param or "").strip().lower()
    if not t:
        return None
    return mch.TYPE_GROUPS.get(t) or [t]


@router.get("/history")
async def get_cost_history(request: Request,
                          material_id: str = Query(""),
                          type: str = Query(""),
                          search: str = Query(""),
                          date_from: str = Query(""),
                          date_to: str = Query(""),
                          limit: int = Query(300, ge=1, le=2000)):
    """Riwayat perubahan harga (HPP rata-rata bergerak) untuk SEMUA jenis barang."""
    await require_auth(request)
    db = get_db()
    data = await mch.history(db, material_id=material_id.strip(), types=_types(type),
                            search=search, date_from=date_from or None,
                            date_to=date_to or None, limit=limit)
    return serialize_doc(data)


@router.get("/materials")
async def list_materials(request: Request,
                        type: str = Query(""),
                        search: str = Query(""),
                        only_with_history: bool = Query(False),
                        limit: int = Query(2000, ge=1, le=5000)):
    """Barang + berapa kali harganya berubah (untuk pemilih di layar)."""
    await require_auth(request)
    if limit < 1:
        raise HTTPException(400, "limit tidak valid")
    return serialize_doc(await mch.materials_index(
        get_db(), types=_types(type), search=search,
        only_with_history=only_with_history, limit=limit))
