"""
Dewi Accessories - Dashboard
Overview and statistics
"""
from fastapi import APIRouter, Request
import uuid
import logging
from datetime import datetime, timezone
from database import get_db
from auth import require_auth

_log = logging.getLogger(__name__)

router = APIRouter(tags=["accessories-dashboard"])

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
    all_accessory_stock as _all_accessory_stock,
)
from core import accessory_valuation  # noqa: E402  FASE 8: nilai persediaan aksesoris

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

@router.get("/dashboard")
async def get_dashboard(request: Request):
    await require_auth(request)
    db = get_db()

    total_items = await db.rahaza_materials.count_documents({"type": "accessory", "active": True})
    stock_map = await _all_accessory_stock(db)
    mats = await db.rahaza_materials.find(
        {"type": "accessory", "active": True}, {"_id": 0}
    ).to_list(5000)

    low_stock_items: list[dict] = []
    out_of_stock = 0
    low_stock = 0
    # FASE 8: KPI nilai persediaan aksesoris + jumlah item yang BELUM DINILAI (HPP 0).
    total_stock_value = 0.0
    unvalued_items = 0
    for m in mats:
        qty = float(stock_map.get(m["id"], 0))
        min_s = float(m.get("min_stock") or 0)
        _cost = accessory_valuation.resolve_unit_cost(m)
        total_stock_value += qty * _cost
        if _cost <= 0:
            unvalued_items += 1
        if qty <= 0:
            out_of_stock += 1
        elif min_s > 0 and qty <= min_s:
            low_stock += 1
            low_stock_items.append({
                "id": m["id"],
                "code": m.get("code", ""),
                "name": m.get("name", ""),
                "stock_qty": qty,
                "min_stock": min_s,
                "unit": m.get("unit", "pcs"),
            })

    # RC-25: SSOT = dewi_accessory_requests (request_type='internal_issuance';
    # status workflow: draft→submitted→allocated→delivered). "Pending" = submitted/allocated.
    # JANGAN repoint acc_loans / acc_purchase_requests — keduanya SELF-CONSISTENT dgn modulnya.
    pending_requests = await db.dewi_accessory_requests.count_documents(
        {"request_type": "internal_issuance", "status": {"$in": ["submitted", "allocated"]}})
    # FASE 10 — KPI "Dipinjam Aktif" DIHAPUS: peminjaman sudah pindah ke domain Aset
    # (dewi_asset_loans) sejak ACC-3, sehingga angka dari `acc_loans` selalu 0 dan
    # justru menyesatkan. Koleksinya di-drop di FASE 10. Penggantinya: "Perlu Diserahkan"
    # (permintaan yang sudah disetujui tapi barangnya belum keluar) — angka yang benar-benar
    # butuh tindakan Admin Aksesoris hari ini.
    ready_to_deliver = await db.dewi_accessory_requests.count_documents(
        {"request_type": "internal_issuance", "status": "allocated"})
    pending_pr = await db.acc_purchase_requests.count_documents({"status": {"$in": ["Draft", "Submitted"]}})
    active_opname = await db.wh_opname_sessions2.find_one({"domain": "accessory", "status": "open"})

    return {
        "total_items": total_items,
        "out_of_stock": out_of_stock,
        "low_stock": low_stock,
        "low_stock_items": low_stock_items[:5],
        "pending_requests": pending_requests,
        "ready_to_deliver": ready_to_deliver,
        "pending_pr": pending_pr,
        "active_opname": active_opname["session_no"] if active_opname else None,
        # FASE 8 — valuasi
        "total_stock_value": round(total_stock_value, 2),
        "unvalued_items": unvalued_items,
    }
