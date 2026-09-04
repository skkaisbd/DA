"""
Dewi Accessories - Requests
Internal requests from divisions
"""
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
import uuid
import logging
from datetime import datetime, timezone
from database import get_db
from core.stock_schema import read_qty, inc_all_qty
from utils.counters import gen_prefixed_number
from auth import require_auth, serialize_doc

_log = logging.getLogger(__name__)

router = APIRouter(tags=["accessories-requests"])

# ── helpers ──────────────────────────────────────────────────────────────────
def _id():    return str(uuid.uuid4())
def _now_iso(): return datetime.now(timezone.utc).isoformat()
def _now():   return datetime.now(timezone.utc)

_VALID_UNITS = {
    "m", "cm", "yard", "inch",
    "kg", "gram", "ton",
    "pcs", "lusin", "kodi", "gross", "helai", "set", "pair",
    "rol", "gulung", "bal", "karton", "pak", "sak",
    "liter", "ml",
}

def _normalize_unit(unit: str) -> str:
    if not unit:
        return "pcs"
    u = str(unit).strip().lower()
    aliases = {
        "piece": "pcs", "pieces": "pcs", "buah": "pcs",
        "meter": "m", "centimeter": "cm",
        "kilogram": "kg", "gr": "gram", "grams": "gram",
        "pasang": "pair", "set/pair": "set",
        "rolls": "rol", "roll": "rol",
        "pack": "pak", "packs": "pak",
        "karton/dus": "karton", "dus": "karton",
    }
    u = aliases.get(u, u)
    return u if u in _VALID_UNITS else "pcs"

# Fase 2.8: helper stok aksesoris KANONIK dipindah ke core.accessory_stock
# (satukan ke rahaza_material_stock flat via stock_service; hilangkan duplikasi Schema-B nested).
from core.accessory_stock import (  # noqa: E402
    get_accessory_location_id as _get_accessory_location_id,
    stock_qty as _stock_qty,
    all_accessory_stock as _all_accessory_stock,
    add_stock as _add_stock,
)

async def _log_movement(db, user: dict, *, material_id: str, mv_type: str, qty: float,
                        notes: str = "", related_ref: str = "", related_type: str = ""):
    mat = await db.rahaza_materials.find_one(
        {"id": material_id}, {"_id": 0, "id": 1, "code": 1, "name": 1, "type": 1, "unit": 1}
    )
    if not mat:
        return
    loc_id = await _get_accessory_location_id(db)
    mvdoc = {
        "id": _id(),
        "material_id": material_id,
        "material": mat,
        "movement_type": mv_type,
        "qty_signed": qty,
        "location": {"id": loc_id, "code": "ZNA-AKSESORIS", "name": "Area Aksesoris"},
        "notes": notes,
        "reference_type": related_type,
        "reference_id": related_ref,
        "created_by": user.get("id", ""),
        "created_at": _now(),
    }
    await db.rahaza_material_movements.insert_one(mvdoc)

async def _enrich_movement(db, mv: dict) -> dict:
    """Lengkapi baris kartu stok dengan konteks permintaan/pinjaman — SSOT SAJA.

    FASE 10: sebelumnya membaca `acc_internal_requests` & `acc_loans` (koleksi legacy
    yang akan di-drop). Sekarang membaca SSOT: `dewi_accessory_requests` untuk
    permintaan internal dan `dewi_asset_loans` untuk peminjaman alat.
    """
    if mv.get("related_req_id"):
        req = await db.dewi_accessory_requests.find_one(
            {"id": mv["related_req_id"]},
            {"_id": 0, "request_code": 1, "divisi": 1, "request_type": 1},
        )
        if req:
            mv["related_request"] = {
                "request_number": req.get("request_code", ""),
                "division": req.get("divisi", ""),
            }
    if mv.get("related_loan_id"):
        loan = await db.dewi_asset_loans.find_one(
            {"id": mv["related_loan_id"]},
            {"_id": 0, "loan_number": 1, "borrower_name": 1},
        )
        if loan:
            mv["related_loan"] = loan
    return mv

# (dead code dibersihkan) _material_to_acc_item duplikat tak terpakai — SSOT serializer item aksesoris ada di routes/dewi_accessories_items.py

# ═════════════════════════════════════════════════════════════════════════════
# FASE 10 — ENDPOINT LEGACY DIMATIKAN (410 GONE)
# ─────────────────────────────────────────────────────────────────────────────
# `/api/acc/internal-requests/*` dulu menulis ke koleksi `acc_internal_requests`,
# padahal SSOT permintaan aksesoris adalah `dewi_accessory_requests`
# (`request_type='internal_issuance'`, P3 TD-009). Efek sampingnya nyata:
#   * KPI "Request Pending" di Dashboard Aksesoris membaca SSOT ⇒ SELALU 0 walau
#     ada permintaan yang dibuat dari UI (karena UI menulis ke koleksi legacy);
#   * inbox/approval SSOT tidak pernah melihat permintaan tersebut;
#   * koleksi legacy tidak bisa di-drop karena masih ada penulis aktif.
# Sejak FASE 10 UI sudah memakai SSOT (yang kini juga MEMOTONG STOK saat deliver),
# jadi endpoint ini dimatikan agar tidak ada jalur menulis ganda.
# Data lama sudah dipindahkan oleh `migrations/migrate_acc_requests_consolidation.py`.
# ═════════════════════════════════════════════════════════════════════════════

_GONE_MSG = (
    "Permintaan internal aksesoris sekarang dilayani SSOT "
    "/api/dewi/accessory-requests (request_type='internal_issuance'): "
    "POST untuk membuat, /{id}/allocate untuk menyetujui, /{id}/deliver untuk "
    "menyerahkan (memotong stok + jurnal), /{id}/reject untuk menolak. "
    "Endpoint lama dimatikan karena menulis ke koleksi ganda."
)


@router.get("/internal-requests")
async def list_internal_requests_gone(request: Request):
    await require_auth(request)
    raise HTTPException(410, _GONE_MSG)


@router.post("/internal-requests")
async def create_internal_request_gone(request: Request):
    await require_auth(request)
    raise HTTPException(410, _GONE_MSG)


@router.put("/internal-requests/{req_id}")
async def update_internal_request_gone(req_id: str, request: Request):
    await require_auth(request)
    raise HTTPException(410, _GONE_MSG)


# ═══════════════════════════════════════════════════════════════
# PEMINJAMAN AKSESORIS (preserved: acc_loans)
# ═══════════════════════════════════════════════════════════════

