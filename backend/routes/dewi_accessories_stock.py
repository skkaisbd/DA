"""
Dewi Accessories - Stock
Stock overview, movements, receive, issue
"""
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
import uuid
import logging
from datetime import datetime, timezone
from database import get_db
from auth import require_auth, serialize_doc, check_role

_log = logging.getLogger(__name__)

router = APIRouter(tags=["accessories-stock"])

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
# FASE 8: valuasi HPP aksesoris (moving average + ringkasan nilai persediaan) +
# poster jurnal supaya mutasi aksesoris masuk buku besar.
from core import accessory_valuation  # noqa: E402
from core import uom as _uom_core  # noqa: E402  (SSOT konversi satuan: input_unit boleh kode satuan)
from core import bom_uom as _bom_uom  # noqa: E402  (cakupan lebar: kemasan + global + kain)
from core import accessory_issue  # noqa: E402  (FASE 10: issue kanonik dipakai juga oleh SSOT request)
from core.stock_rbac import SCRAP_ROLES, SCRAP_FORBIDDEN_MSG  # noqa: E402
from routes.rahaza_posting import (  # noqa: E402
    post_inventory_receive,
    post_accessory_issue,
    post_inventory_adjust,
)

async def _log_movement(db, user: dict, *, material_id: str, mv_type: str, qty: float,
                        notes: str = "", related_ref: str = "", related_type: str = "",
                        unit_cost: float = 0.0, adjustment_reason: str = ""):
    """Catat 1 baris kartu stok aksesoris.

    FASE 8: baris mutasi sekarang MEMBAWA NILAI (`unit_cost` + `value`) supaya laporan
    valuasi & mutasi bernilai bisa dibuat, dan supaya poster jurnal (`post_accessory_issue`
    / `post_inventory_adjust`) bisa membaca nilainya langsung dari dokumen mutasi.
    Return dokumen mutasi (dipakai caller untuk posting jurnal), atau None bila material
    tidak ditemukan.
    """
    mat = await db.rahaza_materials.find_one(
        {"id": material_id}, {"_id": 0, "id": 1, "code": 1, "name": 1, "type": 1, "unit": 1}
    )
    if not mat:
        return None
    loc_id = await _get_accessory_location_id(db)
    unit_cost = float(unit_cost or 0)
    mvdoc = {
        "id": _id(),
        "material_id": material_id,
        "material": mat,
        "material_name": mat.get("name", ""),
        "movement_type": mv_type,
        "qty_signed": qty,
        # `qty` bertanda dipakai oleh poster jurnal generik (post_inventory_adjust)
        "qty": qty,
        "unit": mat.get("unit", "pcs"),
        "unit_cost": round(unit_cost, 4),
        "value": round(abs(float(qty or 0)) * unit_cost, 2),
        "location": {"id": loc_id, "code": "ZNA-AKSESORIS", "name": "Area Aksesoris"},
        "notes": notes,
        "reference_type": related_type,
        "reference_id": related_ref,
        "created_by": user.get("id", ""),
        "created_at": _now(),
    }
    if adjustment_reason:
        mvdoc["adjustment_reason"] = adjustment_reason
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

@router.get("/stock")
async def get_stock_overview(request: Request):
    await require_auth(request)
    db = get_db()
    mats = await db.rahaza_materials.find(
        {"type": "accessory", "active": True}, {"_id": 0}
    ).sort("name", 1).to_list(2000)
    stock_map = await _all_accessory_stock(db)
    result = []
    for m in mats:
        qty = float(stock_map.get(m["id"], 0))
        min_stock = float(m.get("min_stock") or 0)
        # FASE 8: overview stok aksesoris kini membawa NILAI (HPP × qty) supaya layar
        # stok dan laporan keuangan bicara angka yang sama.
        unit_cost = accessory_valuation.resolve_unit_cost(m)
        result.append({
            "id": m["id"],
            "code": m.get("code", ""),
            "name": m.get("name", ""),
            "category": m.get("category", "Umum"),
            "unit": m.get("unit", "pcs"),
            "stock_qty": qty,
            "min_stock": min_stock,
            "unit_cost": round(unit_cost, 4),
            "stock_value": round(qty * unit_cost, 2),
            "valued": unit_cost > 0,
            "cost_method": m.get("cost_method") or ("manual" if unit_cost > 0 else ""),
            "stock_status": (
                "out" if qty <= 0
                else "low" if qty <= min_stock and min_stock > 0
                else "ok"
            ),
        })
    return serialize_doc(result)


@router.get("/stock/movements")
async def get_movements(request: Request):
    await require_auth(request)
    db = get_db()
    sp = request.query_params
    query: dict = {"domain": "accessory"}
    if sp.get("acc_id"):
        query["material_id"] = sp["acc_id"]
    if sp.get("movement_type"):
        # accept both legacy and canonical types
        mt = sp["movement_type"].strip()
        query["$or"] = [
            {"legacy_movement_type": mt.upper()},
            {"type": mt.lower()},
        ]
    docs = await db.rahaza_material_movements.find(query, {"_id": 0}).sort("created_at", -1).limit(500).to_list(500)
    out = [await _enrich_movement(db, d) for d in docs]
    return serialize_doc(out)


@router.post("/stock/receive")
async def receive_stock(request: Request):
    user = await require_auth(request)
    db = get_db()
    body = await request.json()
    acc_id = body.get("acc_id")
    try:
        qty = float(body.get("qty", 0))
    except Exception:
        raise HTTPException(400, "qty harus angka")
    if not acc_id or qty <= 0:
        raise HTTPException(400, "acc_id dan qty > 0 wajib diisi")

    item = await db.rahaza_materials.find_one({"id": acc_id, "type": "accessory", "active": True})
    if not item:
        raise HTTPException(404, "Aksesoris tidak ditemukan")
    
    # NEW: Check if input is in packs, convert to base unit
    # 2026-08-05 — `input_unit` boleh: "base" | "pack" (legacy) | KODE SATUAN dari
    # SSOT UoM (mis. "box", "lusin", "gram"). Perilaku legacy tidak berubah.
    input_unit = body.get("input_unit", "base")  # "base" | "pack" | kode satuan
    pack_size = item.get("pack_size", 1)
    if pack_size <= 0:
        pack_size = 1

    _u = str(input_unit or "base").strip().lower()
    if _u == "pack":
        uom_factor = float(pack_size)
    elif _u in ("", "base"):
        uom_factor = 1.0
    else:
        try:
            uom_factor = float(_bom_uom.factor_to_base(item, _u)[0])
        except _uom_core.UomError as e:
            raise HTTPException(400, str(e))
    qty_in_base_unit = qty * uom_factor
    if uom_factor != 1.0:
        _log.info(f"Receive: {qty} {_u} × {uom_factor} = {qty_in_base_unit} {item.get('unit')}")

    loc_id = await _get_accessory_location_id(db)
    # FASE 8 — VALUASI: harga satuan penerimaan (opsional) memperbarui HPP master dengan
    # metode rata-rata bergerak. `total_cost` diterima sebagai alternatif (harga total →
    # dibagi qty). Bila keduanya kosong → HPP master dipakai apa adanya (tidak berubah).
    #
    # BUG-1 (2026-07-27) — KONVERSI HARGA SAAT INPUT PER KEMASAN.
    # Sebelumnya `unit_cost` dipakai apa adanya walau qty diinput per kemasan, sehingga
    # harga 1 pak (mis. Rp144.000 utk 144 pcs) tersimpan sebagai harga PER PCS →
    # nilai persediaan & jurnal membengkak sebesar `pack_size`.
    # INV-UOM-1: `rahaza_materials.unit_cost` SELALU harga per SATUAN DASAR.
    # `cost_unit` = satuan acuan harga yang diketik user ("pack" | "base").
    # Default mengikuti `input_unit` karena itulah perilaku yang natural bagi user:
    # kalau qty diketik dalam pak, harga yang diketik juga harga per pak.
    cost_unit = (body.get("cost_unit") or input_unit or "base").strip().lower()
    if cost_unit == "pack":
        cost_factor = float(pack_size)
    elif cost_unit in ("", "base"):
        cost_unit, cost_factor = "base", 1.0
    else:
        # harga diketik per satuan kemasan/alternatif (SSOT UoM)
        try:
            cost_factor = float(_bom_uom.factor_to_base(item, cost_unit)[0])
        except _uom_core.UomError:
            cost_unit, cost_factor = "base", 1.0
    try:
        unit_cost_raw = float(body.get("unit_cost") or 0)
    except (TypeError, ValueError):
        raise HTTPException(400, "unit_cost harus berupa angka")
    if unit_cost_raw < 0:
        raise HTTPException(400, "Harga satuan tidak boleh negatif")

    # Harga per satuan dasar (satu-satunya bentuk yang boleh disimpan)
    unit_cost_in = unit_cost_raw / cost_factor if cost_factor > 0 else unit_cost_raw
    if cost_factor != 1.0 and unit_cost_raw > 0:
        _log.info(
            f"Receive cost: {unit_cost_raw} per {cost_unit} "
            f"÷ {cost_factor} = {unit_cost_in} per {item.get('unit')}"
        )

    # `total_cost` selalu harga TOTAL seluruh penerimaan → dibagi qty satuan dasar.
    # Jalur ini sudah benar sejak awal dan tidak terpengaruh `cost_unit`.
    if unit_cost_in <= 0 and body.get("total_cost") not in (None, ""):
        try:
            unit_cost_in = float(body.get("total_cost")) / qty_in_base_unit if qty_in_base_unit else 0
        except (TypeError, ValueError):
            raise HTTPException(400, "total_cost harus berupa angka")
    if unit_cost_in < 0:
        raise HTTPException(400, "Harga satuan tidak boleh negatif")

    qty_before = await _stock_qty(db, acc_id)
    await _add_stock(db, acc_id, loc_id, qty_in_base_unit)
    cost_info = await accessory_valuation.apply_receipt_cost(
        db, acc_id, qty_in_base_unit, unit_cost_in,
        qty_before=qty_before, actor=user,
        notes=body.get("notes", "") or f"Penerimaan {qty_in_base_unit} {item.get('unit', '')}",
    )
    effective_cost = cost_info["new_unit_cost"] or unit_cost_in
    mv = await _log_movement(
        db, user,
        material_id=acc_id, mv_type="receive", qty=qty_in_base_unit,
        notes=body.get("notes", ""),
        related_ref=body.get("reference", ""),
        related_type="receive",
        unit_cost=effective_cost,
    )
    # Jurnal persediaan (Dr Persediaan / Cr AP Clearing) — non-fatal & TRANSPARAN:
    # bila HPP belum ada, penerimaan tetap tercatat tapi FE diberi tahu jurnal gagal.
    je = {"posted": False, "error": "Harga satuan belum diisi — jurnal persediaan tidak dibuat."}
    # ALARM: item bergerak tapi belum dinilai → peringatkan penanggung jawab gudang
    # (anti-spam 1×/24 jam per material). Non-blocking.
    if effective_cost <= 0:
        await accessory_valuation.notify_unvalued(
            db, material=item, movement_type="receive", qty=qty_in_base_unit, actor=user)
    if mv and effective_cost > 0:
        try:
            res = await post_inventory_receive(db, mv, user)
            je = {"posted": bool(res.get("ok")), "je_id": res.get("je_id"),
                  "je_number": res.get("je_number"), "error": res.get("error")}
        except Exception as e:  # noqa: BLE001
            _log.warning(f"[acc-receive] posting jurnal gagal: {e}")
            je = {"posted": False, "error": str(e)}
    new_stock = await _stock_qty(db, acc_id)
    return {
        "ok": True,
        "new_stock_qty": new_stock,
        "qty_received": qty_in_base_unit,
        # Transparansi konversi (BUG-1) — FE bisa menampilkan apa yang terjadi
        "input_qty": qty,
        "input_unit": input_unit,
        "pack_unit": item.get("pack_unit", "pack"),
        "pack_size": pack_size,
        "cost_unit": cost_unit,
        "unit_cost_input": round(unit_cost_raw, 4),
        "unit_cost_in": round(unit_cost_in, 4),
        "unit_cost": effective_cost,
        "old_unit_cost": cost_info["old_unit_cost"],
        "cost_changed": cost_info["changed"],
        "cost_method": cost_info["method"],
        "value": round(qty_in_base_unit * effective_cost, 2),
        "stock_value": round(new_stock * effective_cost, 2),
        "je": je,
    }


@router.post("/stock/issue")
async def issue_stock(request: Request):
    """Keluarkan stok aksesoris (bernilai + berjurnal).

    FASE 10: logikanya dipindah ke `core/accessory_issue.py` supaya jalur SSOT
    permintaan internal (`POST /api/dewi/accessory-requests/{id}/deliver`) memakai
    kode yang PERSIS SAMA — prasyarat agar `acc_internal_requests` bisa di-drop.
    """
    user = await require_auth(request)
    db = get_db()
    body = await request.json()
    try:
        res = await accessory_issue.issue_accessory(
            db, user,
            acc_id=body.get("acc_id"), qty=body.get("qty", 0),
            input_unit=body.get("input_unit", "base"),
            notes=body.get("notes", ""),
            ref_type=body.get("ref_type", "manual"),
            ref_id=body.get("ref_id", ""),
        )
    except accessory_issue.IssueError as e:
        raise HTTPException(getattr(e, "status", 400), str(e))
    return JSONResponse({
        "ok": True,
        "new_qty": res["new_qty"],
        "qty_issued": res["qty_issued"],
        "unit_cost": res["unit_cost"],
        "value": res["value"],
        "stock_value": res["stock_value"],
        "je": res["je"],
    }, status_code=201)


@router.post("/stock/scrap")
async def scrap_stock(request: Request):
    """FASE 8 — SCRAP / SUSUT aksesoris (write-off nilai persediaan).

    Berbeda dari `issue` (barang dipakai produksi ⇒ Dr WIP), scrap = barang HILANG/RUSAK
    sehingga nilainya dihapuskan sebagai kerugian: `post_inventory_adjust` dengan
    `adjustment_reason='scrap'` → **Dr Beban Scrap (6-4300) / Cr Persediaan (1-1401)**.

    RBAC lebih ketat dari mutasi biasa (lihat `core/stock_rbac.py`): tim packing TIDAK
    boleh melakukan write-off.
    """
    user = await require_auth(request)
    if not check_role(user, SCRAP_ROLES, "inv.stock.manage"):
        raise HTTPException(403, SCRAP_FORBIDDEN_MSG)
    db = get_db()
    body = await request.json()
    acc_id = body.get("acc_id")
    try:
        qty = float(body.get("qty", 0))
    except (TypeError, ValueError):
        raise HTTPException(400, "qty harus angka")
    reason = (body.get("reason") or "").strip()
    if not acc_id or qty <= 0:
        raise HTTPException(400, "acc_id dan qty > 0 wajib diisi")
    if not reason:
        raise HTTPException(400, "Alasan scrap wajib diisi (untuk jejak audit & jurnal).")

    item = await db.rahaza_materials.find_one({"id": acc_id, "type": "accessory", "active": True})
    if not item:
        raise HTTPException(404, "Aksesoris tidak ditemukan")

    pack_size = item.get("pack_size", 1) or 1
    if pack_size <= 0:
        pack_size = 1
    qty_base = qty * pack_size if body.get("input_unit") == "pack" else qty

    current = await _stock_qty(db, acc_id)
    if current < qty_base:
        raise HTTPException(400, f"Stok tidak cukup untuk di-scrap. Stok saat ini: {current}")

    await _add_stock(db, acc_id, await _get_accessory_location_id(db), -qty_base)
    unit_cost = accessory_valuation.resolve_unit_cost(item)
    mv = await _log_movement(
        db, user,
        material_id=acc_id, mv_type="scrap", qty=-qty_base,
        notes=(body.get("notes") or ""),
        related_type="scrap", related_ref=reason,
        unit_cost=unit_cost, adjustment_reason="scrap",
    )
    je = {"posted": False,
          "error": "Harga satuan belum diisi — jurnal kerugian scrap tidak dibuat."}
    if unit_cost <= 0:
        await accessory_valuation.notify_unvalued(
            db, material=item, movement_type="scrap", qty=qty_base, actor=user)
    if mv and unit_cost > 0:
        try:
            res = await post_inventory_adjust(db, mv, user)
            je = {"posted": bool(res.get("ok")), "je_id": res.get("je_id"),
                  "je_number": res.get("je_number"), "error": res.get("error")}
        except Exception as e:  # noqa: BLE001
            _log.warning(f"[acc-scrap] posting jurnal gagal: {e}")
            je = {"posted": False, "error": str(e)}
    new_qty = await _stock_qty(db, acc_id)
    return JSONResponse({
        "ok": True,
        "new_qty": new_qty,
        "qty_scrapped": qty_base,
        "reason": reason,
        "unit_cost": round(unit_cost, 4),
        "value": round(qty_base * unit_cost, 2),
        "je": je,
    }, status_code=201)


# ═══════════════════════════════════════════════════════════════
# ⚠️  DEPRECATED (P3 TD-009 — Session #11.10)
# ─────────────────────────────────────────────────────────────────
# INTERNAL REQUESTS — superseded by SSOT `dewi_accessory_requests`
# with `request_type='internal_issuance'`. New client code MUST
# target `/api/dewi/accessory-requests` (routes/dewi_accessory_requests.py).
#
# Routes here remain functional for backward compat (1-week monitor
# before deletion). Stock-deduction side effect on `Issued` status
# remains in place — when migrating, the new endpoint will need an
# equivalent allocate/deliver hook (planned for follow-up).
#
# Migration script: migrations/migrate_acc_requests_consolidation.py
# Logger.info on legacy hits emitted by module-level import below.
# ═══════════════════════════════════════════════════════════════

DIVISI_OPTIONS = ["Produksi", "Cutting", "CMT", "Gudang", "Kantor", "SDM", "QC", "Packing", "Marketing", "Lainnya"]

_log.info(
    "[DEPRECATION] /api/acc/internal-requests/* is DEPRECATED — superseded by "
    "/api/dewi/accessory-requests (request_type='internal_issuance'). See P3 TD-009."
)


