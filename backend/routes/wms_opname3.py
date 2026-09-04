"""wms_opname3 — STOCK OPNAME scan-driven & sadar-lokasi (Fase 4).

Prinsip (dikonfirmasi user):
  * Sumber kebenaran hitung = SCAN barang satu-satu (1 scan = +1 unit). Barcode = KODE MATERIAL/SKU.
  * Scan TERUS-MENERUS tanpa confirm per-scan. Confirm/approval SEKALI di akhir (gate supervisor).
  * Konteks bin di-set via scan barcode bin ATAU pilih manual (bin wajib, metode input fleksibel).
  * Salah lokasi = tetap dihitung di bin aktif + label "salah lokasi" (informasi, tidak auto-relokasi).
  * Approval supervisor WAJIB sebelum stok berubah + lewati rekonsiliasi FINANCE (JE inventory adjust).

Model rekonsiliasi (KUNCI): canonical delta per material = Σ_bin_scope (counted − expected_SNAPSHOT).
  Bukan (counted − canonical) → stok "belum dirak" (unshelved) tidak tersentuh; item salah-lokasi
  otomatis menjadi unshelved (self-consistent tanpa relokasi otomatis).

Koleksi:
  wh_opname3_sessions : {id, session_no, scope_type, scope_id, scope_label, status, snapshot[], summary,
                         created_by/at, submitted_at, approved_by/at, notes}
  wh_opname3_counts   : {id, session_id, bin_id, material_id, counted_qty, salah_lokasi,
                         expected_bin_id, expected_bin_label, updated_at}
Status: counting → submitted → approved | rejected ; counting → cancelled.
"""
import uuid
import logging
from datetime import datetime, timezone
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Request, Query
from pydantic import BaseModel, Field

from database import get_db
from auth import require_auth, serialize_doc, log_activity
from routes.shared import can_act
from core import stock_service
from core import uom as _uom  # SSOT konversi satuan (multi-UOM)
from core import bom_uom as _bom_uom  # cakupan lebar: kemasan + global + kain
from utils.counters import gen_prefixed_number
from routes.rahaza_inventory_shared import _log_movement
from routes.rahaza_posting import post_inventory_adjust

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/wms/opname3", tags=["wms-opname3"])

SESS = "wh_opname3_sessions"
CNT = "wh_opname3_counts"
POS = "wh_positions"

APPROVE_ROLES = ["admin", "admin_gudang", "supervisor", "supervisor_produksi", "manajer", "manager"]


def _uid(): return str(uuid.uuid4())
def _now(): return datetime.now(timezone.utc)


def _unit_cost(mat: dict) -> float:
    return float((mat or {}).get("unit_cost") or (mat or {}).get("hpp") or 0)


def _scan_to_base(mat: dict, qty: float, input_uom: str) -> tuple[float, dict]:
    """Konversi qty hitung fisik → satuan dasar. Kosong = perilaku lama (sudah dasar)."""
    code = (input_uom or "").strip().lower()
    if not code or not mat or code == _uom.base_uom_of(mat):
        return qty, {}
    try:
        # cakupan lebar (kemasan material + satuan global + kain) — sama dengan
        # daftar satuan yang ditawarkan layar (GET /rahaza/materials/uom-options)
        factor, source = _bom_uom.factor_to_base(mat, code)
    except _uom.UomError as e:
        raise HTTPException(400, str(e))
    return round(float(qty) * factor, 4), {
        "input_qty": qty, "input_uom": code, "uom_factor": factor, "uom_source": source,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Models
class SessionCreateIn(BaseModel):
    scope_type: str = Field("all", description="all|building|zone|rack")
    scope_id: str = ""
    notes: str = ""


class ScanIn(BaseModel):
    session_id: str
    bin_id: str = ""
    bin_barcode: str = ""
    item_material_id: str = ""
    item_barcode: str = ""
    # FASE 14 — `ge=0` menutup qty NEGATIF di level model. Sengaja `ge` bukan `gt`:
    # handler memakai `float(data.qty or 1)` sehingga qty=0 BERARTI 1 (perilaku
    # lama dipertahankan), sedangkan qty negatif kini ditolak 422 sebelum masuk
    # handler. Guard handler (`qty <= 0` → 400) tetap ada sebagai lapis kedua.
    qty: float = Field(1, ge=0)
    # Opsional (INV-UOM-2): satuan hitung fisik. Petugas boleh men-scan/menghitung
    # per kemasan ("1 karton") — nilainya dikonversi ke satuan dasar sebelum
    # disimpan sehingga variance & penyesuaian stok tetap dalam satuan dasar.
    # Tanpa field ini perilaku lama TIDAK berubah.
    input_uom: str = ""


class SessionRefIn(BaseModel):
    session_id: str
    notes: str = ""


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
async def _scope_positions(db, scope_type: str, scope_id: str) -> List[dict]:
    q = {}
    if scope_type == "building":
        q["building_id"] = scope_id
    elif scope_type == "zone":
        q["zone_id"] = scope_id
    elif scope_type == "rack":
        q["rack_id"] = scope_id
    return await db[POS].find(q, {"_id": 0}).sort([("shelf_no", 1), ("slot_no", 1)]).to_list(20000)


async def _scope_label(db, scope_type: str, scope_id: str) -> str:
    if scope_type == "all":
        return "Semua Lokasi"
    coll = {"building": "wh_buildings", "zone": "wh_zones", "rack": "wh_racks"}.get(scope_type)
    if not coll or not scope_id:
        return scope_type
    doc = await db[coll].find_one({"id": scope_id}, {"_id": 0, "code": 1, "name": 1})
    if not doc:
        return scope_type
    return f"{doc.get('code','')} - {doc.get('name','')}".strip(" -")


async def _build_snapshot(db, positions: List[dict]) -> List[dict]:
    """Snapshot expected per bin TERISI (occupied) dalam scope."""
    snap = []
    # label lookups
    b_ids = {p.get("building_id") for p in positions}
    z_ids = {p.get("zone_id") for p in positions}
    r_ids = {p.get("rack_id") for p in positions}
    bmap = {b["id"]: b async for b in db.wh_buildings.find({"id": {"$in": list(b_ids)}}, {"_id": 0})}
    zmap = {z["id"]: z async for z in db.wh_zones.find({"id": {"$in": list(z_ids)}}, {"_id": 0})}
    rmap = {r["id"]: r async for r in db.wh_racks.find({"id": {"$in": list(r_ids)}}, {"_id": 0})}
    for p in positions:
        if not p.get("material_id") or float(p.get("qty") or 0) <= 0:
            continue
        b = bmap.get(p.get("building_id")) or {}
        z = zmap.get(p.get("zone_id")) or {}
        r = rmap.get(p.get("rack_id")) or {}
        full = " / ".join([x for x in [b.get("code"), z.get("code"), r.get("code"), p.get("label")] if x])
        snap.append({
            "bin_id": p.get("id"), "bin_barcode": p.get("barcode"),
            "bin_label": p.get("label"), "full_label": full,
            "material_id": p.get("material_id"), "material_code": p.get("material_code"),
            "material_name": p.get("material_name"),
            "expected_qty": float(p.get("qty") or 0), "unit": p.get("unit") or "pcs",
        })
    return snap


async def _resolve_item(db, material_id: str, barcode: str) -> Optional[dict]:
    if material_id:
        return await db.rahaza_materials.find_one({"id": material_id}, {"_id": 0})
    code = (barcode or "").strip()
    if not code:
        return None
    return await db.rahaza_materials.find_one(
        {"$or": [{"code": code}, {"sku": code}, {"barcode": code}]}, {"_id": 0})


async def _variance(db, session: dict) -> dict:
    """Hitung variance per material (counted − expected_snapshot) + daftar salah-lokasi."""
    snap = session.get("snapshot", [])
    expected_by_mat = {}
    mat_meta = {}
    for s in snap:
        mid = s["material_id"]
        expected_by_mat[mid] = expected_by_mat.get(mid, 0) + float(s.get("expected_qty") or 0)
        mat_meta[mid] = {"code": s.get("material_code"), "name": s.get("material_name"), "unit": s.get("unit")}
    counts = await db[CNT].find({"session_id": session["id"]}, {"_id": 0}).to_list(50000)
    counted_by_mat = {}
    salah_lokasi = []
    for c in counts:
        mid = c["material_id"]
        counted_by_mat[mid] = counted_by_mat.get(mid, 0) + float(c.get("counted_qty") or 0)
        if c.get("salah_lokasi") and float(c.get("counted_qty") or 0) > 0:
            salah_lokasi.append(c)
    # meta untuk material yang tak ada di snapshot (mis. ditemukan di bin kosong / belum dirak)
    missing_ids = [m for m in counted_by_mat if m not in mat_meta]
    if missing_ids:
        async for m in db.rahaza_materials.find({"id": {"$in": missing_ids}}, {"_id": 0}):
            mat_meta[m["id"]] = {"code": m.get("code"), "name": m.get("name"), "unit": m.get("unit")}
    lines = []
    tot_var_qty = 0.0
    tot_var_val = 0.0
    for mid in set(list(expected_by_mat.keys()) + list(counted_by_mat.keys())):
        exp = float(expected_by_mat.get(mid, 0))
        cnt = float(counted_by_mat.get(mid, 0))
        var = round(cnt - exp, 4)
        meta = mat_meta.get(mid, {})
        mat = await db.rahaza_materials.find_one({"id": mid}, {"_id": 0, "unit_cost": 1, "hpp": 1})
        uc = _unit_cost(mat)
        val = round(var * uc, 2)
        lines.append({
            "material_id": mid, "material_code": meta.get("code"), "material_name": meta.get("name"),
            "unit": meta.get("unit") or "pcs",
            "expected_qty": round(exp, 4), "counted_qty": round(cnt, 4),
            "variance_qty": var, "unit_cost": uc, "variance_value": val,
        })
        if var != 0:
            tot_var_qty += var
            tot_var_val += val
    lines.sort(key=lambda x: (x["variance_qty"] == 0, x.get("material_code") or ""))
    return {
        "lines": lines,
        "salah_lokasi": serialize_doc(salah_lokasi),
        "totals": {
            "materials_counted": len(counted_by_mat),
            "materials_with_variance": sum(1 for x in lines if x["variance_qty"] != 0),
            "total_variance_qty": round(tot_var_qty, 4),
            "total_variance_value": round(tot_var_val, 2),
            "salah_lokasi_count": len(salah_lokasi),
        },
    }


# ─────────────────────────────────────────────────────────────────────────────
# Endpoints
@router.post("/sessions")
async def create_session(data: SessionCreateIn, request: Request):
    user = await require_auth(request)
    db = get_db()
    if data.scope_type not in ("all", "building", "zone", "rack"):
        raise HTTPException(400, "scope_type harus all|building|zone|rack")
    if data.scope_type != "all" and not data.scope_id:
        raise HTTPException(400, "scope_id wajib untuk scope building/zone/rack")
    positions = await _scope_positions(db, data.scope_type, data.scope_id)
    snapshot = await _build_snapshot(db, positions)
    session_no = await gen_prefixed_number(db, SESS, "session_no", f"OPN-{_now().strftime('%Y%m')}-", 4)
    doc = {
        "id": _uid(), "session_no": session_no,
        "scope_type": data.scope_type, "scope_id": data.scope_id or None,
        "scope_label": await _scope_label(db, data.scope_type, data.scope_id),
        "status": "counting",
        "snapshot": snapshot,
        "bins_in_scope": len(positions),
        "occupied_bins": len(snapshot),
        "notes": data.notes or "",
        "created_by": user.get("id", ""), "created_by_name": user.get("name", ""),
        "created_at": _now(), "submitted_at": None, "approved_at": None, "approved_by": None,
        "summary": None,
    }
    await db[SESS].insert_one(dict(doc))
    await log_activity(user.get("id", ""), user.get("name", ""), "opname_create", SESS,
                       f"Opname {session_no} scope={doc['scope_label']} ({len(snapshot)} bin terisi)")
    return serialize_doc(doc)


@router.get("/sessions")
async def list_sessions(request: Request, status: Optional[str] = None, limit: int = 100):
    await require_auth(request)
    db = get_db()
    q = {}
    if status:
        q["status"] = status
    rows = await db[SESS].find(q, {"_id": 0, "snapshot": 0}).sort("created_at", -1).limit(int(limit)).to_list(500)
    return serialize_doc(rows)


@router.get("/sessions/{session_id}")
async def get_session(session_id: str, request: Request):
    await require_auth(request)
    db = get_db()
    sess = await db[SESS].find_one({"id": session_id}, {"_id": 0})
    if not sess:
        raise HTTPException(404, "Sesi opname tidak ditemukan")
    counts = await db[CNT].find({"session_id": session_id}, {"_id": 0}).to_list(50000)
    variance = await _variance(db, sess)
    return {"session": serialize_doc(sess), "counts": serialize_doc(counts), "variance": variance}


@router.get("/resolve-bin")
async def resolve_bin(request: Request, barcode: str, session_id: Optional[str] = None):
    await require_auth(request)
    db = get_db()
    pos = await db[POS].find_one({"barcode": barcode.strip()}, {"_id": 0})
    if not pos:
        raise HTTPException(404, "Bin tidak ditemukan")
    if session_id:
        sess = await db[SESS].find_one({"id": session_id}, {"_id": 0, "scope_type": 1, "scope_id": 1})
        if sess and sess.get("scope_type") != "all":
            key = {"building": "building_id", "zone": "zone_id", "rack": "rack_id"}[sess["scope_type"]]
            if pos.get(key) != sess.get("scope_id"):
                raise HTTPException(400, "Bin di luar cakupan sesi opname ini")
    return serialize_doc(pos)


@router.get("/resolve-item")
async def resolve_item(request: Request, barcode: str):
    await require_auth(request)
    db = get_db()
    mat = await _resolve_item(db, "", barcode)
    if not mat:
        raise HTTPException(404, f"Barang dengan kode/SKU '{barcode}' tidak ditemukan")
    return serialize_doc(mat)


@router.post("/scan")
async def scan(data: ScanIn, request: Request):
    """1 scan = +qty (default 1) ke (session, bin, material). Cepat, tanpa confirm per-scan."""
    await require_auth(request)
    db = get_db()
    sess = await db[SESS].find_one({"id": data.session_id}, {"_id": 0})
    if not sess:
        raise HTTPException(404, "Sesi opname tidak ditemukan")
    if sess.get("status") != "counting":
        raise HTTPException(400, f"Sesi tidak dalam mode counting (status: {sess.get('status')})")

    # Resolve active bin (scan/select). Bin WAJIB.
    pos = None
    if data.bin_id:
        pos = await db[POS].find_one({"id": data.bin_id}, {"_id": 0})
    elif data.bin_barcode:
        pos = await db[POS].find_one({"barcode": data.bin_barcode.strip()}, {"_id": 0})
    if not pos:
        raise HTTPException(400, "Bin aktif belum dipilih/di-scan (bin wajib)")

    # Resolve item → material
    mat = await _resolve_item(db, data.item_material_id, data.item_barcode)
    if not mat:
        raise HTTPException(404, f"Barang tidak dikenal (kode/SKU: '{data.item_barcode or data.item_material_id}')")

    qty = float(data.qty or 1)
    if qty <= 0:
        raise HTTPException(400, "qty harus > 0")
    qty, uom_trace = _scan_to_base(mat, qty, data.input_uom)

    # salah_lokasi? bandingkan material yg di-scan dgn material yang DIHARAPKAN di bin aktif (snapshot).
    snap = sess.get("snapshot", [])
    bin_expected = next((s for s in snap if s["bin_id"] == pos["id"]), None)
    expected_bin_for_mat = next((s for s in snap if s["material_id"] == mat["id"]), None)
    salah_lokasi = not (bin_expected and bin_expected["material_id"] == mat["id"])

    key = {"session_id": data.session_id, "bin_id": pos["id"], "material_id": mat["id"]}
    await db[CNT].update_one(
        key,
        {"$inc": {"counted_qty": qty},
         "$setOnInsert": {"id": _uid(), "bin_barcode": pos.get("barcode"),
                          "bin_label": pos.get("label"),
                          "material_code": mat.get("code"), "material_name": mat.get("name"),
                          "unit": mat.get("unit") or "pcs"},
         "$set": {"salah_lokasi": salah_lokasi,
                  "expected_bin_id": (expected_bin_for_mat or {}).get("bin_id"),
                  "expected_bin_label": (expected_bin_for_mat or {}).get("full_label"),
                  "updated_at": _now(),
                  **({"last_" + k: v for k, v in uom_trace.items()} if uom_trace else {})}},
        upsert=True,
    )
    row = await db[CNT].find_one(key, {"_id": 0})
    total_scanned = await db[CNT].aggregate([
        {"$match": {"session_id": data.session_id}},
        {"$group": {"_id": None, "t": {"$sum": "$counted_qty"}}}
    ]).to_list(1)
    return {
        "ok": True,
        "material_id": mat["id"], "material_code": mat.get("code"), "material_name": mat.get("name"),
        "bin_id": pos["id"], "bin_barcode": pos.get("barcode"), "bin_label": pos.get("label"),
        "counted_qty": float(row.get("counted_qty") or 0),
        "salah_lokasi": salah_lokasi,
        "base_uom": _uom.base_uom_of(mat),
        "converted_qty": qty,
        **({"uom": uom_trace} if uom_trace else {}),
        "expected_bin_label": (expected_bin_for_mat or {}).get("full_label") if salah_lokasi else None,
        "session_total_scanned": float((total_scanned[0]["t"] if total_scanned else 0)),
    }


@router.post("/scan-undo")
async def scan_undo(data: ScanIn, request: Request):
    """Kurangi (session, bin, material) sebesar qty (floor 0). Untuk koreksi salah scan."""
    await require_auth(request)
    db = get_db()
    sess = await db[SESS].find_one({"id": data.session_id}, {"_id": 0, "status": 1})
    if not sess or sess.get("status") != "counting":
        raise HTTPException(400, "Sesi tidak dalam mode counting")
    pos = None
    if data.bin_id:
        pos = await db[POS].find_one({"id": data.bin_id}, {"_id": 0, "id": 1})
    elif data.bin_barcode:
        pos = await db[POS].find_one({"barcode": data.bin_barcode.strip()}, {"_id": 0, "id": 1})
    mat = await _resolve_item(db, data.item_material_id, data.item_barcode)
    if not pos or not mat:
        raise HTTPException(404, "Bin/barang tidak dikenal")
    key = {"session_id": data.session_id, "bin_id": pos["id"], "material_id": mat["id"]}
    row = await db[CNT].find_one(key, {"_id": 0})
    if not row:
        return {"ok": True, "counted_qty": 0}
    new_qty = max(0.0, float(row.get("counted_qty") or 0) - _scan_to_base(mat, float(data.qty or 1), data.input_uom)[0])
    if new_qty <= 0:
        await db[CNT].delete_one(key)
        new_qty = 0.0
    else:
        await db[CNT].update_one(key, {"$set": {"counted_qty": new_qty, "updated_at": _now()}})
    return {"ok": True, "counted_qty": new_qty}


@router.post("/submit")
async def submit_session(data: SessionRefIn, request: Request):
    """Selesai scan → hitung variance & kunci untuk approval (belum ubah stok)."""
    user = await require_auth(request)
    db = get_db()
    sess = await db[SESS].find_one({"id": data.session_id}, {"_id": 0})
    if not sess:
        raise HTTPException(404, "Sesi opname tidak ditemukan")
    if sess.get("status") != "counting":
        raise HTTPException(400, f"Hanya sesi counting yang bisa submit (status: {sess.get('status')})")
    variance = await _variance(db, sess)
    await db[SESS].update_one({"id": data.session_id}, {"$set": {
        "status": "submitted", "submitted_at": _now(),
        "submitted_by": user.get("id", ""), "submitted_by_name": user.get("name", ""),
        "summary": variance["totals"], "notes": data.notes or sess.get("notes", ""),
    }})
    await log_activity(user.get("id", ""), user.get("name", ""), "opname_submit", SESS,
                       f"Opname {sess.get('session_no')} submitted — {variance['totals']}")
    sess = await db[SESS].find_one({"id": data.session_id}, {"_id": 0})
    return {"session": serialize_doc(sess), "variance": variance}


@router.post("/approve")
async def approve_session(data: SessionRefIn, request: Request):
    """GATE SUPERVISOR. Terapkan rekonsiliasi: qty bin + stok kanonik (delta) + JE finance."""
    user = await require_auth(request)
    # 2026-08-06 — gerbang izin terpusat (fallback aman): `wh.opname.approve`.
    if not can_act(user, "wh.opname.approve", "wh.opname.manage", "warehouse.approve",
                   legacy_roles=APPROVE_ROLES):
        raise HTTPException(403, "Hanya supervisor/admin gudang yang boleh approve opname")
    db = get_db()
    sess = await db[SESS].find_one({"id": data.session_id}, {"_id": 0})
    if not sess:
        raise HTTPException(404, "Sesi opname tidak ditemukan")
    if sess.get("status") != "submitted":
        raise HTTPException(400, f"Hanya sesi submitted yang bisa di-approve (status: {sess.get('status')})")

    variance = await _variance(db, sess)
    snap = sess.get("snapshot", [])
    counts = await db[CNT].find({"session_id": sess["id"]}, {"_id": 0}).to_list(50000)

    # index counts (bin, material) → counted
    cnt_idx = {}
    for c in counts:
        cnt_idx[(c["bin_id"], c["material_id"])] = float(c.get("counted_qty") or 0)

    posting_results = []
    adjustments = []
    # (1) Rekonsiliasi kanonik per material by DELTA snapshot.
    for ln in variance["lines"]:
        delta = ln["variance_qty"]
        if delta == 0:
            continue
        _ref = {"source": "opname", "session_id": sess["id"], "session_no": sess.get("session_no")}
        _actor = {"id": user.get("id", ""), "email": user.get("email", "")}
        try:
            await stock_service.adjust_material(ln["material_id"], delta, ref=_ref, actor=_actor, db=db)
        except Exception as e:
            log.exception("opname adjust_material gagal")
            posting_results.append({"material_id": ln["material_id"], "ok": False, "error": f"stock: {e}"})
            continue
        # movement + finance JE (idempotent per movement)
        mv = await _log_movement(
            db, user, type="adjust", material_id=ln["material_id"],
            material_name=ln.get("material_name"), qty=delta,
            unit_cost=ln.get("unit_cost") or 0, adjustment_reason="opname",
            from_location_id=None, to_location_id=None,
            ref_type="opname", ref_id=sess["id"], notes=f"Opname {sess.get('session_no')}",
        )
        try:
            pr = await post_inventory_adjust(db, mv, user)
        except Exception as e:
            log.exception("opname post_inventory_adjust gagal")
            pr = {"ok": False, "error": str(e)}
        posting_results.append({"material_id": ln["material_id"], "material_code": ln.get("material_code"),
                                "delta": delta, "movement_id": mv["id"], "posting": pr})
        adjustments.append({"material_id": ln["material_id"], "delta": delta})

    # (2) Update qty bin utk MATERIAL YANG DIHARAPKAN di tiap bin (placement truth).
    #     Item salah-lokasi TIDAK ditulis ke placement (jadi unshelved) — sesuai keputusan 3a.
    for s in snap:
        counted_here = cnt_idx.get((s["bin_id"], s["material_id"]), 0.0)
        if counted_here <= 0:
            await db[POS].update_one({"id": s["bin_id"]}, {"$set": {
                "qty": 0, "material_id": None, "material_code": None,
                "material_name": None, "status": "empty", "last_updated": _now()}})
        elif counted_here != s.get("expected_qty"):
            await db[POS].update_one({"id": s["bin_id"]}, {"$set": {
                "qty": counted_here, "status": "occupied", "last_updated": _now()}})

    summary = {**variance["totals"], "adjustments": adjustments,
               "je_posted": sum(1 for p in posting_results if p.get("posting", {}).get("ok"))}
    await db[SESS].update_one({"id": sess["id"]}, {"$set": {
        "status": "approved", "approved_at": _now(),
        "approved_by": user.get("id", ""), "approved_by_name": user.get("name", ""),
        "summary": summary, "posting_results": posting_results,
    }})
    await log_activity(user.get("id", ""), user.get("name", ""), "opname_approve", SESS,
                       f"Opname {sess.get('session_no')} approved — {summary}")
    sess = await db[SESS].find_one({"id": sess["id"]}, {"_id": 0})
    return {"session": serialize_doc(sess), "variance": variance, "posting_results": posting_results}


@router.post("/reject")
async def reject_session(data: SessionRefIn, request: Request):
    user = await require_auth(request)
    # 2026-08-06 — gerbang izin terpusat (fallback aman): `wh.opname.approve`.
    if not can_act(user, "wh.opname.approve", "wh.opname.manage", "warehouse.approve",
                   legacy_roles=APPROVE_ROLES):
        raise HTTPException(403, "Hanya supervisor/admin gudang yang boleh menolak opname")
    db = get_db()
    sess = await db[SESS].find_one({"id": data.session_id}, {"_id": 0, "status": 1, "session_no": 1})
    if not sess:
        raise HTTPException(404, "Sesi opname tidak ditemukan")
    if sess.get("status") != "submitted":
        raise HTTPException(400, "Hanya sesi submitted yang bisa ditolak")
    await db[SESS].update_one({"id": data.session_id}, {"$set": {
        "status": "rejected", "rejected_at": _now(),
        "rejected_by": user.get("id", ""), "rejected_by_name": user.get("name", ""),
        "reject_reason": data.notes or ""}})
    return {"ok": True, "status": "rejected"}


@router.post("/cancel")
async def cancel_session(data: SessionRefIn, request: Request):
    user = await require_auth(request)
    db = get_db()
    sess = await db[SESS].find_one({"id": data.session_id}, {"_id": 0, "status": 1, "created_by": 1})
    if not sess:
        raise HTTPException(404, "Sesi opname tidak ditemukan")
    if sess.get("status") not in ("counting", "submitted"):
        raise HTTPException(400, "Sesi ini tidak bisa dibatalkan")
    await db[SESS].update_one({"id": data.session_id}, {"$set": {
        "status": "cancelled", "cancelled_at": _now(),
        "cancelled_by": user.get("id", "")}})
    return {"ok": True, "status": "cancelled"}
