"""
Session 13 — P1-9: Client SLA Dashboard + P1-10: Smart Lead Time Calculator
- GET /api/maklon/sla/dashboard — aggregated SLA metrics per client
- GET /api/maklon/sla/client/{client_id} — detailed SLA for one client
- POST /api/maklon/sla/lead-time/estimate — Smart Lead Time Calculator
"""
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional
from fastapi import APIRouter, Request, Query, HTTPException, Depends
from routes.production_rbac import deny_external_dep
from pydantic import BaseModel, Field
from database import get_db
from auth import require_auth
from routes._maklon_adapter import legacy_orders_view as _lmo

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/maklon/sla", tags=["maklon-sla"], dependencies=[Depends(deny_external_dep)])
def _now():
    return datetime.now(timezone.utc)


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
#  HELPER: Parse date string or datetime
# ═══════════════════════════════════════════════════════════════════════════

def _parse_date(d) -> Optional[datetime]:
    if d is None:
        return None
    if isinstance(d, datetime):
        return d.replace(tzinfo=timezone.utc) if d.tzinfo is None else d
    if isinstance(d, str):
        for fmt in ["%Y-%m-%dT%H:%M:%S", "%Y-%m-%d", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S.%f"]:
            try:
                return datetime.strptime(d[:len(fmt)], fmt).replace(tzinfo=timezone.utc)
            except Exception:
                logging.getLogger(__name__).debug("suppressed exception", exc_info=True)
    return None


def _calc_lead_days(order_date, deadline_date) -> Optional[float]:
    """Total lead time days from order to deadline."""
    start = _parse_date(order_date)
    end = _parse_date(deadline_date)
    if start and end and end > start:
        return (end - start).days
    return None


def _is_on_time(deadline_date, completed_at) -> Optional[bool]:
    """Returns True if completed before/on deadline, False if late, None if not completed."""
    if not completed_at:
        return None
    d = _parse_date(deadline_date)
    c = _parse_date(completed_at)
    if d and c:
        return c <= d
    return None


# ═══════════════════════════════════════════════════════════════════════════
#  P1-9: SLA DASHBOARD (All Clients)
# ═══════════════════════════════════════════════════════════════════════════

@router.get("/dashboard")
async def get_sla_dashboard(
    request: Request,
    days: int = Query(90, description="Period dalam hari"),
):
    """
    P1-9: Aggregated SLA metrics per client.
    Metrics: on-time rate, avg lead time, # orders, # late.
    """
    await require_auth(request)
    db = get_db()

    since = _now() - timedelta(days=days)

    # Get all orders in period (read via _lmo adapter → dewi_maklon_pos SSOT)
    orders = await _lmo(db).find(
        {"order_date": {"$gte": since.isoformat()}},
        {"_id": 0}
    ).to_list(length=2000)

    # Get all clients for name mapping
    clients_raw = await db.dewi_maklon_clients.find({}, {"_id": 0}).to_list(length=500)
    client_map = {c["id"]: c for c in clients_raw}

    # Group by client
    client_stats = {}
    for order in orders:
        cid = order.get("client_id")
        if not cid:
            continue
        if cid not in client_stats:
            client_stats[cid] = {
                "client_id": cid,
                "client_name": client_map.get(cid, {}).get("name", cid),
                "client_code": client_map.get(cid, {}).get("code", ""),
                "total_orders": 0,
                "completed_orders": 0,
                "on_time": 0,
                "late": 0,
                "lead_times": [],
                "total_qty": 0,
            }
        s = client_stats[cid]
        s["total_orders"] += 1
        s["total_qty"] += order.get("quantity", 0)

        stage = order.get("stage", "")
        completed_at = order.get("completed_at")

        if stage in ("completed", "invoiced") or completed_at:
            s["completed_orders"] += 1
            ot = _is_on_time(order.get("deadline_date"), completed_at or _now().isoformat())
            if ot is True:
                s["on_time"] += 1
            elif ot is False:
                s["late"] += 1

        ld = _calc_lead_days(order.get("order_date"), order.get("deadline_date"))
        if ld:
            s["lead_times"].append(ld)

    # Calculate derived metrics
    results = []
    for cid, s in client_stats.items():
        completed = s["completed_orders"]
        on_time_rate = (s["on_time"] / completed * 100) if completed > 0 else None
        avg_lead_time = (sum(s["lead_times"]) / len(s["lead_times"])) if s["lead_times"] else None
        results.append({
            "client_id": cid,
            "client_name": s["client_name"],
            "client_code": s["client_code"],
            "total_orders": s["total_orders"],
            "completed_orders": completed,
            "on_time": s["on_time"],
            "late": s["late"],
            "on_time_rate": round(on_time_rate, 1) if on_time_rate is not None else None,
            "avg_lead_days": round(avg_lead_time, 1) if avg_lead_time is not None else None,
            "total_qty": s["total_qty"],
            "sla_status": "good" if (on_time_rate or 0) >= 90 else (
                "warning" if (on_time_rate or 0) >= 70 else "poor"
            ),
        })

    # Sort by on_time_rate descending
    results.sort(key=lambda x: x["on_time_rate"] or -1, reverse=True)

    # Overall aggregate
    total_completed = sum(r["completed_orders"] for r in results)
    total_on_time = sum(r["on_time"] for r in results)
    overall_rate = (total_on_time / total_completed * 100) if total_completed > 0 else None
    all_leads = [r["avg_lead_days"] for r in results if r["avg_lead_days"]]

    return ok(
        data=results,
        meta={
            "period_days": days,
            "total_clients": len(results),
            "total_orders": sum(r["total_orders"] for r in results),
            "total_completed": total_completed,
            "overall_on_time_rate": round(overall_rate, 1) if overall_rate is not None else None,
            "overall_avg_lead_days": round(sum(all_leads) / len(all_leads), 1) if all_leads else None,
        }
    )


@router.get("/client/{client_id}")
async def get_client_sla(
    client_id: str,
    request: Request,
    days: int = Query(90),
):
    """
    P1-9: Detailed SLA for one client — order list + per-stage timeline.
    """
    await require_auth(request)
    db = get_db()

    since = _now() - timedelta(days=days)

    client = await db.dewi_maklon_clients.find_one({"id": client_id}, {"_id": 0})
    if not client:
        raise HTTPException(status_code=404, detail="Client tidak ditemukan")

    orders = await _lmo(db).find(
        {"client_id": client_id, "order_date": {"$gte": since.isoformat()}},
        {"_id": 0}
    ).sort("order_date", -1).to_list(length=200)

    order_details = []
    for o in orders:
        ot = _is_on_time(o.get("deadline_date"), o.get("completed_at"))
        ld = _calc_lead_days(o.get("order_date"), o.get("deadline_date"))
        order_details.append({
            "id": o.get("id"),
            "order_code": o.get("order_code"),
            "garment_type": o.get("garment_type"),
            "quantity": o.get("quantity"),
            "order_date": o.get("order_date"),
            "deadline_date": o.get("deadline_date"),
            "completed_at": o.get("completed_at"),
            "stage": o.get("stage"),
            "lead_days": ld,
            "on_time": ot,
            "status": "on_time" if ot is True else ("late" if ot is False else "in_progress"),
        })

    completed = [o for o in order_details if o["status"] in ("on_time", "late")]
    on_time_rate = (sum(1 for o in completed if o["status"] == "on_time") / len(completed) * 100) if completed else None

    return ok(data={
        "client": serialize(client),
        "orders": serialize(order_details),
        "summary": {
            "total": len(orders),
            "completed": len(completed),
            "on_time_rate": round(on_time_rate, 1) if on_time_rate is not None else None,
        }
    })


# ═══════════════════════════════════════════════════════════════════════════
#  P1-10: SMART LEAD TIME CALCULATOR
# ═══════════════════════════════════════════════════════════════════════════

# Base estimates from historical data (days)
BASE_LEAD_TIME = {
    "shirt": 14,
    "blouse": 14,
    "dress": 18,
    "pants": 16,
    "skirt": 12,
    "jacket": 25,
    "coat": 28,
    "uniform": 20,
    "casual": 14,
    "formal": 21,
    "other": 16,
}


class LeadTimeEstimateIn(BaseModel):
    garment_type: str = Field(..., description="Jenis garmen: shirt, blouse, dress, pants, jacket, dll.")
    quantity: int = Field(..., ge=1, description="Jumlah pcs")
    complexity: str = Field(default="medium", description="simple | medium | complex")
    has_embroidery: bool = Field(default=False)
    has_special_material: bool = Field(default=False)
    rush_order: bool = Field(default=False)


@router.post("/lead-time/estimate")
async def estimate_lead_time(
    payload: LeadTimeEstimateIn,
    request: Request,
):
    """
    P1-10: Smart Lead Time Estimator.
    Hitung perkiraan lead time berdasarkan jenis garmen, qty, kompleksitas, workload.
    """
    await require_auth(request)
    db = get_db()

    # Base lead time
    garment_key = payload.garment_type.lower().strip()
    base = BASE_LEAD_TIME.get(garment_key, BASE_LEAD_TIME["other"])

    # Complexity multiplier
    complexity_mult = {"simple": 0.75, "medium": 1.0, "complex": 1.5}.get(payload.complexity.lower(), 1.0)

    # Quantity factor: 1-100pcs=0%, 101-500=+10%, 501-1000=+25%, >1000=+50%
    if payload.quantity <= 100:
        qty_factor = 0.0
    elif payload.quantity <= 500:
        qty_factor = 0.10
    elif payload.quantity <= 1000:
        qty_factor = 0.25
    else:
        qty_factor = 0.50

    # Additions
    embroidery_days = 3 if payload.has_embroidery else 0
    special_material_days = 5 if payload.has_special_material else 0

    # Current workload from active orders (orders in progress)
    active_orders = await _lmo(db).count_documents(
        {"stage": {"$in": ["confirmed", "material_ready", "cutting", "sewing", "qc", "packing"]}}
    )

    # Workload factor: 0-5 active = 0%, 6-15 = +15%, >15 = +30%
    if active_orders <= 5:
        workload_factor = 0.0
    elif active_orders <= 15:
        workload_factor = 0.15
    else:
        workload_factor = 0.30

    # Calculate
    calculated_days = base * complexity_mult * (1 + qty_factor + workload_factor)
    calculated_days += embroidery_days + special_material_days
    calculated_days = round(calculated_days)

    # Rush order reduces by 30% (but adds cost premium note)
    rush_discount = 0
    if payload.rush_order:
        rush_discount = round(calculated_days * 0.3)
        calculated_days = calculated_days - rush_discount

    # Calculate target delivery date
    start = _now()
    target_date = start + timedelta(days=calculated_days)

    # Get historical average for this garment type (last 90 days)
    since90 = _now() - timedelta(days=90)
    historical = await _lmo(db).find(
        {
            "garment_type": {"$regex": garment_key, "$options": "i"},
            "stage": {"$in": ["completed", "invoiced"]},
            "order_date": {"$gte": since90.isoformat()},
        },
        {"order_date": 1, "deadline_date": 1}
    ).to_list(length=50)

    hist_leads = []
    for h in historical:
        ld = _calc_lead_days(h.get("order_date"), h.get("deadline_date"))
        if ld and ld > 0:
            hist_leads.append(ld)

    hist_avg = round(sum(hist_leads) / len(hist_leads), 1) if hist_leads else None

    return ok(data={
        "estimated_days": calculated_days,
        "target_delivery_date": target_date.strftime("%Y-%m-%d"),
        "breakdown": {
            "base_days": base,
            "complexity_mult": complexity_mult,
            "qty_factor_pct": round(qty_factor * 100),
            "workload_factor_pct": round(workload_factor * 100),
            "embroidery_days": embroidery_days,
            "special_material_days": special_material_days,
            "rush_discount_days": rush_discount,
            "active_orders_now": active_orders,
        },
        "historical_avg_days": hist_avg,
        "historical_sample_size": len(hist_leads),
        "complexity": payload.complexity,
        "garment_type": payload.garment_type,
        "quantity": payload.quantity,
        "rush_order": payload.rush_order,
        "recommendation": (
            f"Estimasi {calculated_days} hari ({target_date.strftime('%d %b %Y')}). "
            + (f"Rata-rata historis: {hist_avg} hari. " if hist_avg else "")
            + ("⚠️ Rush order — ada premium biaya." if payload.rush_order else "")
        ),
    })
