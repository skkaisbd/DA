"""
Session 13 — P1-14, P1-15, P1-16: Smart Inventory Features

P1-14: Alert Auto Gudang >90%
- GET /api/warehouse/alerts — rack occupancy alerts (>90% by default)

P1-15: Smart Reorder Point
- GET  /api/warehouse/smart-reorder — materials with smart reorder calc
- POST /api/warehouse/smart-reorder/{material_id} — update reorder point

P1-16: Undo Stock Adjustment (Soft Delete + Restore) — FASE F CANONICAL
- GET  /api/warehouse/stock-adjustments/undo-history — undoable adjustments (N days)
- POST /api/warehouse/stock-adjustments/{ledger_id}/undo — reverse an adjustment
- POST /api/warehouse/stock-adjustments/{ledger_id}/restore — re-apply an adjustment

FASE F (2026-07-25): undo-history/undo/restore MIGRATED to the canonical SSOT
`rahaza_stock_ledger` (op='adjust') + reversal via `core.stock_service.adjust`.
No longer reads `warehouse_movements` nor mutates `rahaza_materials.total_qty`.
"""
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional
from fastapi import APIRouter, Request, Query, HTTPException
from pydantic import BaseModel, Field
from database import get_db
from auth import require_auth
from core import stock_service  # FASE D: onhand kanonik + konsumsi dari rahaza_stock_ledger
from core.stock_schema import read_qty  # FASE F: baca qty kanonik utk reversal undo

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/warehouse", tags=["warehouse-smart"])

# ──────────────────────────────────────────────────────────────────────────────
# DEPRECATION NOTICE (updated FASE F, 2026-07-25)
# ──────────────────────────────────────────────────────────────────────────────
# Modul ini DULU membaca koleksi LEGACY GEN 1 (`warehouse_stock`,
# `warehouse_movements`). Sejak FASE D & FASE F seluruh endpoint di sini sudah
# KANONIK:
#   - /alerts        → low-stock via stock_service.onhand_map (bukan total_qty).
#   - /smart-reorder → on-hand stock_service.onhand_map + konsumsi rahaza_stock_ledger.
#   - /stock-adjustments/* → SSOT rahaza_stock_ledger (op='adjust') + reversal
#                            stock_service.adjust.
# Koleksi legacy `warehouse_stock`/`warehouse_movements` dijadwalkan DROP (Fase F
# migration script). Tidak ada lagi pembaca legacy di file ini.
# ──────────────────────────────────────────────────────────────────────────────
logger.info(
    "[FASE F] dewi_warehouse_smart.py — undo-history/undo/restore kini KANONIK "
    "(rahaza_stock_ledger op='adjust' + stock_service.adjust reversal). "
    "Tidak lagi baca warehouse_movements / tulis rahaza_materials.total_qty."
)


def _now():
    return datetime.now(timezone.utc)


def _coerce_dt(v):
    """Kembalikan datetime tz-aware dari str/datetime; None bila gagal."""
    if v is None:
        return None
    if isinstance(v, datetime):
        return v if v.tzinfo else v.replace(tzinfo=timezone.utc)
    if isinstance(v, str):
        try:
            dt = datetime.fromisoformat(v.replace("Z", "+00:00"))
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except Exception:
            return None
    return None


def ok(data=None, meta=None):
    r = {"success": True}
    if data is not None:
        r["data"] = data
    if meta is not None:
        r["metadata"] = meta
    return r


def serialize(o):
    if isinstance(o, list):
        return [serialize(i) for i in o]
    if isinstance(o, dict):
        return {k: serialize(v) for k, v in o.items() if k != "_id"}
    if isinstance(o, datetime):
        return o.isoformat()
    return o


# ═══════════════════════════════════════════════════════════════════════════
#  P1-14: WAREHOUSE OCCUPANCY ALERTS
# ═══════════════════════════════════════════════════════════════════════════

@router.get("/alerts")
async def get_warehouse_alerts(
    request: Request,
    threshold: int = Query(90, ge=0, le=100, description="Occupancy threshold %"),
):
    """
    P1-14: Warehouse alerts — racks at/above threshold occupancy.
    Also includes low stock alerts.
    """
    await require_auth(request)
    db = get_db()

    # Get rack occupancy
    racks = await db.rahaza_racks.find({}, {"_id": 0}).to_list(length=500)

    high_occupancy = []
    for rack in racks:
        total = rack.get("total_slots", 0)
        occupied = rack.get("occupied", rack.get("occupied_slots", 0))
        if total <= 0:
            continue
        pct = round(occupied / total * 100)
        if pct >= threshold:
            high_occupancy.append({
                "type": "rack_occupancy",
                "severity": "critical" if pct >= 95 else "warning",
                "rack_code": rack.get("rack_code", rack.get("code")),
                "location": rack.get("location", rack.get("zone")),
                "occupied": occupied,
                "total": total,
                "occupancy_pct": pct,
                "message": f"Rak {rack.get('rack_code', rack.get('code'))} mencapai {pct}% kapasitas",
            })

    # Get low stock alerts — W3: SATU definisi "rendah" dari SSOT
    # `core/stock_thresholds`. Dulu blok ini hanya melihat `reorder_point > 0`,
    # sehingga ambang minimum (`min_stock_qty`) yang justru diisi pemilik di
    # Master Item TIDAK PERNAH memicu alert di layar ini.
    from core import stock_thresholds as _th
    low_stock_alerts = await _th.low_stock_alerts(db)
    _th_summary = await _th.summary(db)

    all_alerts = high_occupancy + low_stock_alerts
    all_alerts.sort(key=lambda x: (0 if x["severity"] == "critical" else 1))

    return ok(
        data=all_alerts,
        meta={
            "total_alerts": len(all_alerts),
            "critical": sum(1 for a in all_alerts if a["severity"] == "critical"),
            "warning": sum(1 for a in all_alerts if a["severity"] == "warning"),
            "rack_alerts": len(high_occupancy),
            "stock_alerts": len(low_stock_alerts),
            "threshold_pct": threshold,
            # Kejujuran layar: kalau ambangnya BELUM diisi, "0 alert" bukan berarti
            # stok aman — layar harus mengatakan itu apa adanya.
            "materials_total": _th_summary["total_materials"],
            "materials_with_threshold": _th_summary["with_threshold"],
            "materials_missing_threshold": _th_summary["missing_threshold"],
        }
    )


# ═══════════════════════════════════════════════════════════════════════════
#  P1-15: SMART REORDER POINT
# ═══════════════════════════════════════════════════════════════════════════

@router.get("/smart-reorder")
async def get_smart_reorder(
    request: Request,
    limit: int = Query(50, ge=1, le=200),
):
    """
    P1-15: Smart Reorder Point calculator.
    Calculates recommended reorder point based on:
    - Average daily consumption (from canonical rahaza_stock_ledger last 30 days)
    - Lead time (avg 7 days as default, override-able)
    - Safety stock (20% buffer)
    """
    await require_auth(request)
    db = get_db()
    from core import stock_thresholds as _th

    # Get all active materials
    materials = await db.rahaza_materials.find(
        {"active": True},
        {"_id": 0}
    ).to_list(length=limit)

    mat_ids = [m.get("id") for m in materials if m.get("id")]

    # W3: konsumsi 30 hari & rumus usulan dipindah ke SSOT `core/stock_thresholds`
    # supaya layar "Ambang Stok" (Master Item) dan layar ini TIDAK PERNAH
    # menampilkan usulan yang berbeda untuk material yang sama.
    consumption = await _th.usage_map(db, mat_ids)

    # Stok on-hand KANONIK lintas lokasi (SSOT) — bukan mat.total_qty yg tak terpelihara.
    onhand = await stock_service.onhand_map(mat_ids, db=db) if mat_ids else {}

    results = []
    for mat in materials:
        mat_id = mat.get("id")
        sug = _th.suggest(mat, consumption.get(mat_id))
        smart_rp = sug["suggested_reorder_point"]
        current_rp = float(mat.get("reorder_point", 0))
        current_qty = float(onhand.get(mat_id, 0))

        results.append({
            "material_id": mat_id,
            "name": mat.get("name"),
            "sku": mat.get("sku") or mat.get("code"),
            "unit": mat.get("unit"),
            "current_qty": current_qty,
            "current_reorder_point": current_rp,
            "smart_reorder_point": smart_rp,
            "suggested_min_stock": sug["suggested_min_stock"],
            "min_stock_qty": float(mat.get("min_stock_qty") or 0),
            "avg_daily_consumption": sug["avg_daily_consumption"],
            "lead_time_days": sug["lead_time_days"],
            "safety_stock": sug["safety_stock"],
            "needs_update": abs(smart_rp - current_rp) > 1 if smart_rp > 0 else False,
            "status": _th.status_of(current_qty, _th.resolve_threshold(mat)),
            "movements_30d": sug["movements_30d"],
            "no_usage_data": sug["no_usage_data"],
        })

    # Sort by needs_update first, then by status
    results.sort(key=lambda x: (not x["needs_update"], x["status"] not in ("low", "critical")))

    return ok(
        data=results,
        meta={"total": len(results), "needs_update": sum(1 for r in results if r["needs_update"])}
    )


class UpdateReorderIn(BaseModel):
    reorder_point: float = Field(..., ge=0)
    lead_time_days: Optional[float] = None


@router.put("/smart-reorder/{material_id}")
async def update_smart_reorder(
    material_id: str,
    payload: UpdateReorderIn,
    request: Request,
):
    """P1-15: Update reorder point (and optional lead_time_days) for a material."""
    await require_auth(request)
    db = get_db()

    mat = await db.rahaza_materials.find_one({"id": material_id})
    if not mat:
        raise HTTPException(status_code=404, detail="Material tidak ditemukan")

    update_data = {"reorder_point": payload.reorder_point, "updated_at": _now().isoformat()}
    if payload.lead_time_days is not None:
        update_data["lead_time_days"] = payload.lead_time_days

    await db.rahaza_materials.update_one({"id": material_id}, {"$set": update_data})
    return ok(data={"material_id": material_id, "reorder_point": payload.reorder_point})


# ═══════════════════════════════════════════════════════════════════════════
#  P1-16: UNDO STOCK ADJUSTMENT (Soft Delete + Restore) — FASE F CANONICAL
#  Sumber data: `rahaza_stock_ledger` (op='adjust') — SSOT penyesuaian stok
#  (opname3/manual adjust). Reversal via `stock_service.adjust` (bukan lagi
#  mutasi `rahaza_materials.total_qty` atau baca `warehouse_movements` legacy).
#    - undo   : batalkan efek NET (new_qty = current − delta), tandai soft_deleted.
#    - restore: terapkan ulang (new_qty = current + delta), lepas soft_deleted.
#  Entri reversal (ref.source undo_adjustment/restore_adjustment) DIFILTER dari
#  daftar undoable agar tidak jadi loop tak berujung.
# ═══════════════════════════════════════════════════════════════════════════

_REVERSAL_SOURCES = ["undo_adjustment", "restore_adjustment"]


async def _load_adjust_entry(db, ledger_id: str):
    return await db.rahaza_stock_ledger.find_one({"id": ledger_id, "op": "adjust"})


def _row_qty(row):
    return float(read_qty(row)) if row else 0.0


@router.get("/stock-adjustments/undo-history")
async def get_undo_history(
    request: Request,
    days: int = Query(7, description="Tampilkan history N hari terakhir"),
):
    """
    P1-16 (FASE F): daftar penyesuaian stok KANONIK (rahaza_stock_ledger op='adjust')
    dalam N hari terakhir. `undoable` = belum di-undo; `soft_deleted` = sudah di-undo
    (bisa di-restore). Entri reversal sendiri difilter keluar.
    """
    await require_auth(request)
    db = get_db()

    since = _now() - timedelta(days=days)
    rows = await db.rahaza_stock_ledger.find(
        {
            "op": "adjust",
            "created_at": {"$gte": since},
            "ref.source": {"$nin": _REVERSAL_SOURCES},
        },
        {"_id": 0},
    ).sort("created_at", -1).to_list(length=300)

    # Enrich sku/name/unit dari master rahaza_materials (batch).
    mat_ids = list({r.get("material_id") for r in rows if r.get("material_id")})
    mat_map = {}
    if mat_ids:
        async for m in db.rahaza_materials.find(
            {"id": {"$in": mat_ids}},
            {"_id": 0, "id": 1, "name": 1, "sku": 1, "code": 1, "unit": 1},
        ):
            mat_map[m["id"]] = m

    def to_item(r):
        meta = r.get("meta") or {}
        ref = r.get("ref") or {}
        mat = mat_map.get(r.get("material_id"), {})
        src = str(ref.get("source") or ref.get("ref_type") or "adjustment").lower()
        return {
            "id": r.get("id"),
            "material_id": r.get("material_id"),
            "location_id": r.get("location_id"),
            "sku": mat.get("sku") or mat.get("code") or meta.get("material_code") or r.get("material_id"),
            "material_name": mat.get("name") or meta.get("material_name"),
            "movement_type": "opname" if "opname" in src else "adjustment",
            "qty": r.get("delta"),
            "qty_before": r.get("qty_before"),
            "counted_qty": r.get("counted_qty"),
            "unit": mat.get("unit") or meta.get("unit") or "",
            "created_at": r.get("created_at"),
            "soft_deleted": bool(r.get("soft_deleted")),
            "deleted_by": r.get("deleted_by"),
        }

    items = [to_item(r) for r in rows]
    undoable = [x for x in items if not x["soft_deleted"]]
    deleted = [x for x in items if x["soft_deleted"]]

    return ok(
        data={"undoable": serialize(undoable), "soft_deleted": serialize(deleted)},
        meta={
            "undoable_count": len(undoable),
            "soft_deleted_count": len(deleted),
            "period_days": days,
        }
    )


@router.post("/stock-adjustments/{ledger_id}/undo")
async def undo_stock_adjustment(
    ledger_id: str,
    request: Request,
):
    """
    P1-16 (FASE F): batalkan (undo) satu penyesuaian stok kanonik.
    Membalik efek NET via stock_service.adjust (new = current − delta) lalu menandai
    entri ledger sebagai soft_deleted. Aman terhadap mutasi lain: reversal berbasis
    delta absolut sehingga tidak menimpa perubahan yang terjadi setelahnya.
    """
    user = await require_auth(request)
    db = get_db()

    entry = await _load_adjust_entry(db, ledger_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Penyesuaian stok tidak ditemukan")
    if entry.get("soft_deleted"):
        raise HTTPException(status_code=400, detail="Penyesuaian ini sudah di-undo sebelumnya")

    created_dt = _coerce_dt(entry.get("created_at"))
    if created_dt and (_now() - created_dt).days > 7:
        raise HTTPException(status_code=400, detail="Undo hanya bisa dilakukan dalam 7 hari")

    delta = float(entry.get("delta") or 0)
    material_id = entry.get("material_id")
    location_id = entry.get("location_id")
    actor = {"id": user.get("id"), "name": user.get("name"), "email": user.get("email")}

    if material_id and delta != 0:
        row = await db.rahaza_material_stock.find_one(
            {"material_id": material_id, "location_id": location_id}, {"_id": 0}
        )
        current = _row_qty(row)
        new_qty = round(current - delta, 4)
        if new_qty < 0:
            new_qty = 0.0
        await stock_service.adjust(
            material_id, location_id, new_qty,
            ref={"source": "undo_adjustment", "undo_of": ledger_id, "original_delta": delta},
            actor=actor, db=db,
        )

    await db.rahaza_stock_ledger.update_one(
        {"id": ledger_id},
        {"$set": {
            "soft_deleted": True,
            "deleted_at": _now().isoformat(),
            "deleted_by": user.get("email") or user.get("name") or "unknown",
        }},
    )
    return ok(data={"id": ledger_id, "undone": True})


@router.post("/stock-adjustments/{ledger_id}/restore")
async def restore_stock_adjustment(
    ledger_id: str,
    request: Request,
):
    """
    P1-16 (FASE F): kembalikan (restore) penyesuaian stok yang tadinya di-undo.
    Menerapkan ulang efek delta via stock_service.adjust (new = current + delta) lalu
    melepas flag soft_deleted.
    """
    user = await require_auth(request)
    db = get_db()

    entry = await _load_adjust_entry(db, ledger_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Penyesuaian stok tidak ditemukan")
    if not entry.get("soft_deleted"):
        raise HTTPException(status_code=400, detail="Penyesuaian tidak dalam status soft-deleted")

    delta = float(entry.get("delta") or 0)
    material_id = entry.get("material_id")
    location_id = entry.get("location_id")
    actor = {"id": user.get("id"), "name": user.get("name"), "email": user.get("email")}

    if material_id and delta != 0:
        row = await db.rahaza_material_stock.find_one(
            {"material_id": material_id, "location_id": location_id}, {"_id": 0}
        )
        current = _row_qty(row)
        new_qty = round(current + delta, 4)
        if new_qty < 0:
            new_qty = 0.0
        await stock_service.adjust(
            material_id, location_id, new_qty,
            ref={"source": "restore_adjustment", "restore_of": ledger_id, "original_delta": delta},
            actor=actor, db=db,
        )

    await db.rahaza_stock_ledger.update_one(
        {"id": ledger_id},
        {"$set": {
            "soft_deleted": False,
            "restored_at": _now().isoformat(),
            "restored_by": user.get("email") or user.get("name") or "unknown",
        }},
    )
    return ok(data={"id": ledger_id, "restored": True})
