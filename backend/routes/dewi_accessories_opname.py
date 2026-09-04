"""
Dewi Accessories - Opname
Stock opname sessions (SSOT: wh_opname_sessions2)
"""
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
import uuid
import logging
from datetime import datetime, timezone
from database import get_db
from core.stock_schema import read_qty, inc_all_qty
from utils.counters import gen_prefixed_number
from auth import require_auth, check_role, log_activity

_log = logging.getLogger(__name__)

router = APIRouter(tags=["accessories-opname"])

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
from routes.rahaza_posting import post_inventory_adjust  # FASE G: JE inventory adjust (approval gate)
from core import uom as _uom  # SSOT konversi satuan (multi-UOM)
from core import bom_uom as _bom_uom  # noqa: E402  (cakupan lebar: kemasan + global + kain)

# FASE G: role yang boleh APPROVE/REJECT opname aksesoris (samakan dgn standar Opname3).
APPROVE_ROLES = ["admin", "admin_gudang", "supervisor", "supervisor_produksi",
                 "manajer", "manager", "warehouse_manager", "superadmin", "owner"]

async def _log_movement(db, user: dict, *, material_id: str, mv_type: str, qty: float,
                        notes: str = "", related_ref: str = "", related_type: str = "",
                        adjustment_reason: str = "", unit_cost: float = 0.0):
    mat = await db.rahaza_materials.find_one(
        {"id": material_id}, {"_id": 0, "id": 1, "code": 1, "name": 1, "type": 1, "unit": 1}
    )
    if not mat:
        return None
    loc_id = await _get_accessory_location_id(db)
    ts = _now()
    mvdoc = {
        "id": _id(),
        "material_id": material_id,
        "material": mat,
        # FASE G: top-level fields agar kompatibel dgn post_inventory_adjust (finance JE)
        "material_name": mat.get("name", ""),
        "type": mv_type,
        "movement_type": mv_type,
        "qty": qty,                       # signed delta (dipakai post_inventory_adjust)
        "qty_signed": qty,                # back-compat display accessory
        "unit_cost": unit_cost,
        "adjustment_reason": adjustment_reason,
        "location": {"id": loc_id, "code": "ZNA-AKSESORIS", "name": "Area Aksesoris"},
        "notes": notes,
        "reference_type": related_type,
        "ref_type": related_type,
        "reference_id": related_ref,
        "ref_id": related_ref,
        "created_by": user.get("id", ""),
        "created_at": ts,
        "timestamp": ts,
    }
    await db.rahaza_material_movements.insert_one(dict(mvdoc))
    return mvdoc

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

# Opname-specific helpers
_STATUS_WH_TO_ACC = {"open": "Active", "approved": "Completed", "cancelled": "Cancelled",
                     "pending_approval": "Submitted", "submitted": "Submitted",
                     "rejected": "Rejected", "counted": "Active"}

def _iso_str(ts) -> str:
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
    return {
        "id": item.get("line_id") or item.get("position_id") or "",
        "session_id": session_id,
        "acc_id": item.get("material_id") or item.get("position_id") or "",
        "acc_name": item.get("material_name", ""),
        "acc_code": item.get("material_code", ""),
        "unit": item.get("unit", "pcs"),
        "system_qty": float(item.get("system_qty") or 0),
        "counted_qty": item.get("counted_qty"),
        "diff": item.get("variance"),
        "notes": item.get("notes", ""),
        "counted_by": item.get("counted_by", ""),
        "counted_at": _iso_str(item.get("counted_at")),
    }

def _wh_session_to_acc(s: dict, include_lines: bool = False) -> dict:
    # FASE G fix: expose approval + finance-posting fields yang dipakai FE
    # (StokOpnameTab: je_posted / total_variance_value / total_variance_items /
    #  approved_by / reject_reason). Sebelumnya hilang → UI selalu tampil "0".
    summary = s.get("summary") or {}
    _var_value = s.get("total_variance_value")
    if _var_value is None:
        _var_value = summary.get("total_variance_value")
    out = {
        "id": s.get("id"),
        "ref_number": s.get("session_no") or "",
        "notes": s.get("notes", ""),
        "status": _STATUS_WH_TO_ACC.get(s.get("status", ""), s.get("status", "Active")),
        "raw_status": s.get("status", ""),
        "total_items": s.get("total_items", 0),
        "counted_items": s.get("counted_items", 0),
        "total_variance_items": s.get("total_variance_items", 0) or 0,
        "total_variance_value": float(_var_value or 0),
        "started_by": s.get("created_by", ""),
        "started_at": _iso_str(s.get("created_at")),
        "counted_by": s.get("counted_by", "") or "",
        "submitted_by": s.get("submitted_by", "") or "",
        "submitted_at": _iso_str(s.get("submitted_at")) or "",
        "approved_by": s.get("approved_by", "") or "",
        "approved_at": _iso_str(s.get("approved_at")) or "",
        "rejected_by": s.get("rejected_by", "") or "",
        "rejected_at": _iso_str(s.get("rejected_at")) or "",
        "reject_reason": s.get("reject_reason", "") or "",
        "je_posted": int(summary.get("je_posted") or 0),
        "je_failed": int(summary.get("je_failed") or 0),
        "je_failed_items": summary.get("je_failed_items") or [],
        # Transparansi baris yang stoknya GAGAL di-adjust (mis. total on-hand kurang).
        # Sebelumnya baris seperti ini di-`continue` diam-diam: user melihat sesi
        # "Completed" padahal sebagian selisih tidak pernah diterapkan.
        "stock_failed": int(summary.get("stock_failed") or 0),
        "stock_failed_items": summary.get("stock_failed_items") or [],
        "adjustments_made": int(summary.get("adjustments_made") or 0),
        "summary": summary,
        "completed_by": s.get("approved_by", "") or "",
        "completed_at": _iso_str(s.get("approved_at")) or "",
        "created_at": _iso_str(s.get("created_at")),
        "updated_at": _iso_str(s.get("submitted_at") or s.get("approved_at") or s.get("created_at")),
    }
    if include_lines:
        out["lines"] = [_wh_line_to_acc(it, s.get("id", "")) for it in s.get("count_items", [])]
    return out

async def _next_acc_opname_ref(db) -> str:
    # RC-5 fix: atomic race-safe numbering (was count_documents()+1)
    return await gen_prefixed_number(db, "wh_opname_sessions2", "session_no", "OPNAME-", 4)

@router.get("/opname")
async def list_opname(request: Request):
    await require_auth(request)
    db = get_db()
    sessions = await db.wh_opname_sessions2.find(
        {"domain": "accessory"}, {"_id": 0}
    ).sort("created_at", -1).to_list(500)
    return [_wh_session_to_acc(s, include_lines=False) for s in sessions]


@router.post("/opname")
async def start_opname(request: Request):
    user = await require_auth(request)
    db = get_db()
    body = await request.json()

    active = await db.wh_opname_sessions2.find_one(
        {"domain": "accessory", "status": "open"}, {"_id": 0}
    )
    if active:
        raise HTTPException(400, f"Masih ada sesi opname aktif: {active.get('session_no')}")

    session_id = _id()
    ref = await _next_acc_opname_ref(db)

    # Snapshot semua aksesoris dengan stok sistem (dari SSOT rahaza_material_stock)
    mats = await db.rahaza_materials.find(
        {"type": "accessory", "active": True}, {"_id": 0}
    ).to_list(5000)
    stock_map = await _all_accessory_stock(db)
    count_items = []
    for m in mats:
        count_items.append({
            "line_id": _id(),                          # internal stable id for this row
            "material_id": m["id"],                    # SSOT material reference
            "position_id": m["id"],                    # back-compat alias (acc_id == material_id)
            "material_code": m.get("code", ""),
            "material_name": m.get("name", ""),
            "unit": m.get("unit", "pcs"),
            "system_qty": float(stock_map.get(m["id"], 0)),
            "counted_qty": None,
            "variance": None,
            "variance_pct": None,
            "notes": "",
            "counted": False,
        })

    session = {
        "id": session_id,
        "session_no": ref,
        "mode": "full_count",
        "scope_type": "all",
        "scope_id": "",
        "scope_label": "Aksesoris",
        "domain": "accessory",                          # ← SSOT discriminator
        "status": "open",
        "count_items": count_items,
        "total_items": len(count_items),
        "counted_items": 0,
        "total_variance_items": 0,
        "total_variance_value": 0.0,
        "notes": body.get("notes", ""),
        "created_at": _now(),
        "created_by": user.get("name", user.get("id", "")),
        "counted_by": None,
        "approved_by": None,
        "approved_at": None,
        "closed_at": None,
    }
    await db.wh_opname_sessions2.insert_one(session)
    out = await db.wh_opname_sessions2.find_one({"id": session_id}, {"_id": 0})
    return JSONResponse(_wh_session_to_acc(out, include_lines=True), status_code=201)


@router.get("/opname/{session_id}")
async def get_opname_detail(session_id: str, request: Request):
    await require_auth(request)
    db = get_db()
    session = await db.wh_opname_sessions2.find_one(
        {"id": session_id, "domain": "accessory"}, {"_id": 0}
    )
    if not session:
        raise HTTPException(404, "Sesi tidak ditemukan")
    return _wh_session_to_acc(session, include_lines=True)


@router.put("/opname/{session_id}/count")
async def update_count(session_id: str, request: Request):
    user = await require_auth(request)
    db = get_db()
    body = await request.json()
    acc_id = body.get("acc_id")
    counted_qty = body.get("counted_qty")
    if acc_id is None or counted_qty is None:
        raise HTTPException(400, "acc_id dan counted_qty wajib diisi")

    session = await db.wh_opname_sessions2.find_one(
        {"id": session_id, "domain": "accessory"}
    )
    if not session:
        raise HTTPException(404, "Sesi tidak ditemukan")
    if session.get("status") != "open":
        raise HTTPException(400, "Sesi sudah selesai atau dibatalkan")

    items = session.get("count_items", [])
    target = None
    for item in items:
        # match either material_id or legacy position_id (kept identical for acc opname)
        if item.get("material_id") == acc_id or item.get("position_id") == acc_id:
            target = item
            break
    if target is None:
        raise HTTPException(404, "Baris opname tidak ditemukan")

    system_qty = float(target.get("system_qty") or 0)

    # Konversi satuan hitung fisik → satuan dasar (INV-UOM-2).
    # Kasus nyata dari audit: petugas menghitung "3 pak" tetapi sistem mencatat
    # "3 pcs" sehingga stok 432 pcs terpangkas jadi 3 pcs dan selisihnya
    # langsung dijurnal sebagai kerugian. `counted_uom` opsional; bila tidak
    # dikirim, perilakunya sama seperti sebelumnya (dianggap satuan dasar).
    counted_uom = (body.get("counted_uom") or body.get("input_uom") or "").strip().lower()
    counted_qty_f = float(counted_qty)
    uom_trace = {}
    if counted_uom:
        mat = await db.rahaza_materials.find_one({"id": acc_id}, {"_id": 0})
        if mat and counted_uom != _uom.base_uom_of(mat):
            try:
                # cakupan lebar (kemasan + satuan global + kain) supaya sama
                # dengan daftar satuan yang ditawarkan layar
                factor, source = _bom_uom.factor_to_base(mat, counted_uom)
            except _uom.UomError as e:
                raise HTTPException(400, str(e))
            uom_trace = {"counted_input_qty": counted_qty_f,
                         "counted_input_uom": counted_uom,
                         "uom_factor": factor, "uom_source": source}
            counted_qty_f = round(counted_qty_f * factor, 4)

    variance = counted_qty_f - system_qty
    variance_pct = (variance / system_qty * 100.0) if system_qty > 0 else (100.0 if counted_qty_f > 0 else 0.0)

    target["counted_qty"] = counted_qty_f
    target["variance"] = variance
    target["variance_pct"] = variance_pct
    target["notes"] = body.get("notes", "")
    target["counted_by"] = user.get("name", user.get("id", ""))
    target["counted_at"] = _now_iso()
    target["counted"] = True
    if uom_trace:
        target.update(uom_trace)

    counted_items = sum(1 for it in items if it.get("counted"))
    total_variance_items = sum(1 for it in items if it.get("counted") and (it.get("variance") or 0) != 0)
    await db.wh_opname_sessions2.update_one(
        {"id": session_id, "domain": "accessory"},
        {"$set": {
            "count_items": items,
            "counted_items": counted_items,
            "total_variance_items": total_variance_items,
            "counted_by": user.get("name", user.get("id", "")),
        }},
    )
    return {"ok": True, "diff": variance, "counted_qty_base": counted_qty_f, **uom_trace}


# ── FASE G: helper submit/approve (standar Opname3: approval supervisor + finance JE) ──
def _variance_counts(items: list):
    counted_items = sum(1 for it in items if it.get("counted"))
    variance_items = sum(1 for it in items if it.get("counted") and (it.get("variance") or 0) != 0)
    return counted_items, variance_items


async def _do_submit(db, user, session):
    """open → pending_approval. Kunci sesi utk approval; BELUM ubah stok."""
    items = session.get("count_items", [])
    counted_items, variance_items = _variance_counts(items)
    now = _now()
    await db.wh_opname_sessions2.update_one(
        {"id": session["id"], "domain": "accessory"},
        {"$set": {
            "status": "pending_approval",
            "submitted_at": now,
            "submitted_by": user.get("name", user.get("id", "")),
            "counted_items": counted_items,
            "total_variance_items": variance_items,
        }},
    )
    await log_activity(user.get("id", ""), user.get("name", ""), "acc_opname_submit",
                       "wh_opname_sessions2",
                       f"Opname aksesoris {session.get('session_no')} diajukan — {variance_items} selisih")
    return {"ok": True, "status": "pending_approval",
            "counted_items": counted_items, "variance_items": variance_items}


@router.post("/opname/{session_id}/submit")
async def submit_opname(session_id: str, request: Request):
    """FASE G: Ajukan sesi opname untuk approval supervisor (open → pending_approval).
    Belum mengubah stok. Adjustment + posting finance baru diterapkan saat approve."""
    user = await require_auth(request)
    db = get_db()
    session = await db.wh_opname_sessions2.find_one({"id": session_id, "domain": "accessory"})
    if not session:
        raise HTTPException(404, "Sesi tidak ditemukan")
    if session.get("status") != "open":
        raise HTTPException(400, f"Hanya sesi aktif yang bisa diajukan (status: {session.get('status')})")
    if not any(it.get("counted") for it in session.get("count_items", [])):
        raise HTTPException(400, "Belum ada item yang dihitung. Hitung minimal 1 item sebelum mengajukan.")
    return await _do_submit(db, user, session)


@router.post("/opname/{session_id}/approve")
async def approve_opname(session_id: str, request: Request):
    """FASE G: GATE SUPERVISOR. pending_approval → approved.
    Terapkan adjustment stok KANONIK (stock_service) + posting FINANCE (JE inventory adjust)."""
    user = await require_auth(request)
    if not check_role(user, APPROVE_ROLES):
        raise HTTPException(403, "Hanya supervisor/admin gudang yang boleh approve opname aksesoris")
    db = get_db()
    session = await db.wh_opname_sessions2.find_one({"id": session_id, "domain": "accessory"})
    if not session:
        raise HTTPException(404, "Sesi tidak ditemukan")
    if session.get("status") not in ("pending_approval", "submitted"):
        raise HTTPException(400, f"Hanya sesi yang diajukan yang bisa di-approve (status: {session.get('status')})")

    loc_id = await _get_accessory_location_id(db)
    items = session.get("count_items", [])
    _ref = {"source": "accessory_opname", "session_id": session_id, "session_no": session.get("session_no")}
    _actor = {"id": user.get("id", ""), "name": user.get("name", ""), "email": user.get("email", "")}

    adjustments_made = 0
    total_variance_value = 0.0
    posting_results = []
    je_posted = 0
    je_failed = 0
    je_failed_items = []
    stock_failed = 0
    stock_failed_items = []
    for ln in items:
        if not ln.get("counted"):
            continue
        diff = float(ln.get("variance") or 0)
        if diff == 0:
            continue
        material_id = ln.get("material_id") or ln.get("position_id")
        if not material_id:
            continue
        mat = await db.rahaza_materials.find_one(
            {"id": material_id}, {"_id": 0, "unit_cost": 1, "hpp": 1, "name": 1})
        unit_cost = float((mat or {}).get("unit_cost") or (mat or {}).get("hpp") or 0)
        # (1) stok kanonik via stock_service
        try:
            await _add_stock(db, material_id, loc_id, diff, actor=_actor, ref=_ref)
        except Exception as e:
            # TRANSPARANSI: jangan pernah menelan kegagalan ini. Sebelumnya baris
            # gagal hanya di-`continue` → sesi tampak "Completed" padahal selisihnya
            # tidak pernah diterapkan dan tak ada satu pun petunjuk di UI.
            _log.exception("acc opname add_stock gagal")
            stock_failed += 1
            stock_failed_items.append({
                "material_id": material_id,
                "name": (mat or {}).get("name", "") or ln.get("material_name", ""),
                "code": ln.get("material_code", ""),
                "delta": diff,
                "reason": str(e),
            })
            posting_results.append({"material_id": material_id, "ok": False, "error": f"stock: {e}"})
            continue
        # (2) movement (rahaza_material_movements) + (3) finance JE (idempotent per movement)
        mv = await _log_movement(
            db, user, material_id=material_id, mv_type="adjust", qty=diff,
            related_type="opname", related_ref=session_id, adjustment_reason="opname",
            unit_cost=unit_cost, notes=f"Opname Aksesoris {session.get('session_no')}",
        )
        pr = {"ok": False, "error": "movement gagal"}
        if mv:
            try:
                pr = await post_inventory_adjust(db, mv, user)
            except Exception as e:
                _log.exception("acc opname post_inventory_adjust gagal")
                pr = {"ok": False, "error": str(e)}
        if pr.get("ok"):
            je_posted += 1
        else:
            # transparansi: penyesuaian stok berhasil tapi JE gagal (paling sering unit_cost=0)
            je_failed += 1
            je_failed_items.append({
                "material_id": material_id,
                "name": (mat or {}).get("name", "") or ln.get("material_name", ""),
                "code": ln.get("material_code", ""),
                "delta": diff,
                "reason": pr.get("error", "unknown"),
            })
        posting_results.append({"material_id": material_id, "delta": diff,
                                "movement_id": (mv or {}).get("id"), "posting": pr})
        adjustments_made += 1
        total_variance_value += abs(diff * unit_cost)

    now = _now()
    summary = {"adjustments_made": adjustments_made, "je_posted": je_posted,
               "je_failed": je_failed, "je_failed_items": je_failed_items[:50],
               "stock_failed": stock_failed, "stock_failed_items": stock_failed_items[:50],
               "total_variance_value": round(total_variance_value, 2)}
    await db.wh_opname_sessions2.update_one(
        {"id": session_id, "domain": "accessory"},
        {"$set": {
            "status": "approved",
            "approved_by": user.get("name", user.get("id", "")),
            "approved_at": now,
            "closed_at": now,
            "total_variance_value": round(total_variance_value, 2),
            "summary": summary,
            "posting_results": posting_results,
        }},
    )
    await log_activity(user.get("id", ""), user.get("name", ""), "acc_opname_approve",
                       "wh_opname_sessions2",
                       f"Opname aksesoris {session.get('session_no')} disetujui — {summary}")
    return {"ok": True, "status": "approved", "adjustments_made": adjustments_made,
            "je_posted": je_posted, "je_failed": je_failed, "je_failed_items": je_failed_items[:50],
            "stock_failed": stock_failed, "stock_failed_items": stock_failed_items[:50],
            "total_variance_value": round(total_variance_value, 2),
            "posting_results": posting_results}


@router.post("/opname/{session_id}/reject")
async def reject_opname(session_id: str, request: Request):
    """FASE G: GATE SUPERVISOR. pending_approval → rejected (tanpa ubah stok)."""
    user = await require_auth(request)
    if not check_role(user, APPROVE_ROLES):
        raise HTTPException(403, "Hanya supervisor/admin gudang yang boleh menolak opname aksesoris")
    db = get_db()
    try:
        body = await request.json()
    except Exception:
        body = {}
    session = await db.wh_opname_sessions2.find_one({"id": session_id, "domain": "accessory"})
    if not session:
        raise HTTPException(404, "Sesi tidak ditemukan")
    if session.get("status") not in ("pending_approval", "submitted"):
        raise HTTPException(400, "Hanya sesi yang diajukan yang bisa ditolak")
    now = _now()
    await db.wh_opname_sessions2.update_one(
        {"id": session_id, "domain": "accessory"},
        {"$set": {
            "status": "rejected",
            "rejected_at": now,
            "rejected_by": user.get("name", user.get("id", "")),
            "reject_reason": (body or {}).get("reason", "") or (body or {}).get("notes", ""),
        }},
    )
    await log_activity(user.get("id", ""), user.get("name", ""), "acc_opname_reject",
                       "wh_opname_sessions2", f"Opname aksesoris {session.get('session_no')} ditolak")
    return {"ok": True, "status": "rejected"}


@router.post("/opname/{session_id}/complete")
async def complete_opname(session_id: str, request: Request):
    """DEPRECATED (FASE G): opname aksesoris kini butuh approval supervisor + posting finance.
    Endpoint ini TIDAK lagi auto-apply stok — perilaku = submit (open → pending_approval).
    Gunakan /submit lalu /approve (supervisor). Dipertahankan sbg alias kompat FE lama."""
    user = await require_auth(request)
    db = get_db()
    session = await db.wh_opname_sessions2.find_one({"id": session_id, "domain": "accessory"})
    if not session:
        raise HTTPException(404, "Sesi tidak ditemukan")
    if session.get("status") != "open":
        raise HTTPException(400, "Sesi sudah selesai atau dibatalkan")
    if not any(it.get("counted") for it in session.get("count_items", [])):
        raise HTTPException(400, "Belum ada item yang dihitung.")
    res = await _do_submit(db, user, session)
    res["deprecated"] = True
    res["message"] = "Opname diajukan untuk approval supervisor (auto-apply dihapus di FASE G)."
    return res


@router.post("/opname/{session_id}/cancel")
async def cancel_opname(session_id: str, request: Request):
    user = await require_auth(request)
    db = get_db()
    res = await db.wh_opname_sessions2.update_one(
        {"id": session_id, "domain": "accessory"},
        {"$set": {
            "status": "cancelled",
            "closed_at": _now(),
            "approved_by": user.get("name", user.get("id", "")),
        }},
    )
    if res.matched_count == 0:
        raise HTTPException(404, "Sesi tidak ditemukan")
    return {"ok": True}


# ═══════════════════════════════════════════════════════════════
# PURCHASE REQUEST (preserved: acc_purchase_requests)
# ═══════════════════════════════════════════════════════════════
