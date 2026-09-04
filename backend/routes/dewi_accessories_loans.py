"""
Dewi Accessories - Loans
Accessory loans and returns
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

router = APIRouter(tags=["accessories-loans"])

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
# FASE 10 — PEMINJAMAN AKSESORIS LEGACY DIMATIKAN (410 GONE)
# ─────────────────────────────────────────────────────────────────────────────
# ACC-3 sudah memindahkan peminjaman ke domain ASET (`dewi_asset_loans`,
# /api/assets/loans): yang dipinjam-kembalikan adalah UNIT FISIK ber-nomor, bukan
# stok habis pakai. `POST /loans` sudah 410 sejak ACC-3, tapi `GET /loans` dan
# `PUT /loans/{id}/return` masih membaca/menulis `acc_loans` — itulah satu-satunya
# jalur baca aktif yang membuat koleksi ini belum bisa di-drop (FASE 10 §prasyarat).
#
# Semua pinjaman lama yang masih Active ditutup lebih dulu oleh migrasi terpandu
# `migrations/close_legacy_acc_loans.py` (mengembalikan stok + kartu stok + bisa
# rollback), setelah itu koleksinya di-drop lewat
# `migrations/drop_legacy_collections_guided.py --group accessory_legacy`.
# ═════════════════════════════════════════════════════════════════════════════

_LOANS_GONE_MSG = (
    "Peminjaman alat/aset dikelola di Manajemen Aset → Peminjaman Alat "
    "(/api/assets/loans). Data pinjaman aksesoris lama sudah ditutup & diarsipkan "
    "(migrations/close_legacy_acc_loans.py). Aksesoris habis pakai memakai jalur "
    "Request Internal → Approval → Serahkan."
)


@router.get("/loans")
async def list_loans_gone(request: Request):
    await require_auth(request)
    raise HTTPException(410, _LOANS_GONE_MSG)


@router.post("/loans")
async def create_loan_gone(request: Request):
    await require_auth(request)
    raise HTTPException(410, _LOANS_GONE_MSG)


@router.put("/loans/{loan_id}/return")
async def return_loan_gone(loan_id: str, request: Request):
    await require_auth(request)
    raise HTTPException(410, _LOANS_GONE_MSG)


# ═══════════════════════════════════════════════════════════════
# STOK OPNAME — SSOT-backed (2026-05-23 migration)
# Storage: wh_opname_sessions2 (domain="accessory", count_items embedded)
# Status mapping: open <-> Active, approved <-> Completed, cancelled <-> Cancelled
# API contract preserved: ref_number, status, lines[].acc_id/acc_name/system_qty/diff
# ═══════════════════════════════════════════════════════════════

# ── adapter helpers: project wh_opname_sessions2 doc → legacy acc shape ──────
_STATUS_WH_TO_ACC = {"open": "Active", "approved": "Completed", "cancelled": "Cancelled",
                     "pending_approval": "Active", "counted": "Active"}


def _iso_str(ts) -> str:
    """Convert any datetime-ish into ISO string; pass-through if already str."""
    if not ts:
        return ""
    if isinstance(ts, str):
        return ts
    if hasattr(ts, "isoformat"):
        try:
            return ts.isoformat()
        except Exception:
            return str(ts)
    return str(ts)


def _wh_line_to_acc(item: dict, session_id: str) -> dict:
    """Project one wh_opname_sessions2.count_items[] entry into legacy acc_opname_lines shape."""
    return {
        "id": item.get("line_id") or item.get("position_id") or "",
        "session_id": session_id,
        "acc_id": item.get("material_id") or item.get("position_id") or "",
        "acc_name": item.get("material_name", ""),
        "acc_code": item.get("material_code", ""),
        "unit": item.get("unit", "pcs"),
        "system_qty": float(item.get("system_qty") or 0),
        "counted_qty": item.get("counted_qty"),  # may be None
        "diff": item.get("variance"),            # may be None (kept under "diff" for FE back-compat)
        "notes": item.get("notes", ""),
        "counted_by": item.get("counted_by", ""),
        "counted_at": _iso_str(item.get("counted_at")),
    }


def _wh_session_to_acc(s: dict, include_lines: bool = False) -> dict:
    """Project a wh_opname_sessions2 doc into legacy acc_opname_sessions shape."""
    out = {
        "id": s.get("id"),
        "ref_number": s.get("session_no") or "",
        "notes": s.get("notes", ""),
        "status": _STATUS_WH_TO_ACC.get(s.get("status", ""), s.get("status", "Active")),
        "total_items": s.get("total_items", 0),
        "counted_items": s.get("counted_items", 0),
        "started_by": s.get("created_by", ""),
        "started_at": _iso_str(s.get("created_at")),
        "completed_by": s.get("approved_by", "") or "",
        "completed_at": _iso_str(s.get("approved_at")) or "",
        "created_at": _iso_str(s.get("created_at")),
        "updated_at": _iso_str(s.get("submitted_at") or s.get("approved_at") or s.get("created_at")),
    }
    if include_lines:
        out["lines"] = [_wh_line_to_acc(it, s.get("id", "")) for it in s.get("count_items", [])]
    return out


async def _next_acc_opname_ref(db) -> str:
    """Assign next legacy-style reference number (OPNAME-NNNN) for accessory opname."""
    # RC-5 fix: atomic race-safe numbering (was count_documents()+1)
    return await gen_prefixed_number(db, "wh_opname_sessions2", "session_no", "OPNAME-", 4)


# ── endpoints ────────────────────────────────────────────────────────────────

