"""
Session 18 — P2-7: Predictive Maintenance (Produksi)

Features:
- Machine health monitoring based on maintenance history + downtime
- Predictive scoring using rule-based heuristics + AI advice (Emergent LLM)
- Maintenance log CRUD
- Auto-generated maintenance schedule recommendation
- Dashboard with machine health overview

Endpoints (prefix: /api/production/predictive-maintenance)
- GET    /machines                          — list machines with health score
- GET    /machines/{id}/health             — detailed health for one machine
- POST   /machines/{id}/predict            — AI-based prediction & advice
- GET    /maintenance-logs                 — list maintenance logs
- POST   /maintenance-logs                 — create maintenance log
- DELETE /maintenance-logs/{id}            — delete log
- GET    /dashboard                        — high-level overview
"""
# ruff: noqa: E741
import os
import uuid
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional
from fastapi import APIRouter, Request, Query, HTTPException
from pydantic import BaseModel, Field
from database import get_db
from auth import require_auth

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/production/predictive-maintenance", tags=["predictive-maintenance"])

LOG_COL = "rahaza_maintenance_logs"
MACHINES_COL = "rahaza_machines"
DOWNTIME_COL = "rahaza_downtime_events"

LLM_KEY = os.environ.get("EMERGENT_LLM_KEY", "")
LLM_MODEL = ("openai", "gpt-5.1")


def _now():
    return datetime.now(timezone.utc)


def _now_iso():
    return _now().isoformat()


def _serialize(obj):
    if isinstance(obj, dict):
        obj.pop("_id", None)
        return {k: _serialize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_serialize(i) for i in obj]
    if isinstance(obj, datetime):
        return obj.isoformat()
    return obj


# ═════════════════════════════════════════════════════════════════════
# Models
# ═════════════════════════════════════════════════════════════════════
class MaintenanceLogIn(BaseModel):
    machine_id: str
    machine_name: Optional[str] = None
    maintenance_type: str = Field("preventive")  # preventive | corrective | inspection
    description: str
    performed_at: Optional[str] = None  # ISO date string
    technician: Optional[str] = None
    cost: Optional[float] = Field(default=0, ge=0)
    parts_replaced: list = []
    next_maintenance_due: Optional[str] = None


def _machine_health(machine: dict, logs: list, downtimes: list) -> dict:
    """Compute health score 0..100 with risk classification."""
    score = 100.0
    factors: list = []

    # Last maintenance recency (preventive)
    pm_logs = [l for l in logs if l.get("maintenance_type") == "preventive"]
    pm_logs.sort(key=lambda l: l.get("performed_at") or "", reverse=True)
    last_pm = pm_logs[0] if pm_logs else None
    days_since_pm = None
    if last_pm and last_pm.get("performed_at"):
        try:
            last_dt = datetime.fromisoformat(last_pm["performed_at"].replace("Z", "+00:00"))
            days_since_pm = (datetime.now(timezone.utc) - last_dt).days
        except Exception:
            days_since_pm = None

    if days_since_pm is None:
        score -= 30
        factors.append({"factor": "No preventive maintenance recorded", "impact": -30})
    elif days_since_pm > 180:
        score -= 35
        factors.append({"factor": f"Last PM {days_since_pm} hari lalu (>6 bln)", "impact": -35})
    elif days_since_pm > 90:
        score -= 18
        factors.append({"factor": f"Last PM {days_since_pm} hari lalu (>3 bln)", "impact": -18})
    elif days_since_pm > 60:
        score -= 8
        factors.append({"factor": f"Last PM {days_since_pm} hari lalu", "impact": -8})

    # Corrective maintenance frequency in last 90 days
    cutoff = datetime.now(timezone.utc) - timedelta(days=90)
    cm_recent = [
        l
        for l in logs
        if l.get("maintenance_type") == "corrective"
        and l.get("performed_at")
        and l["performed_at"] >= cutoff.isoformat()
    ]
    cm_count = len(cm_recent)
    if cm_count >= 4:
        score -= 25
        factors.append({"factor": f"{cm_count} corrective dalam 90 hari", "impact": -25})
    elif cm_count >= 2:
        score -= 12
        factors.append({"factor": f"{cm_count} corrective dalam 90 hari", "impact": -12})
    elif cm_count == 1:
        score -= 5
        factors.append({"factor": "1 corrective dalam 90 hari", "impact": -5})

    # Downtime frequency
    dt_count = len(downtimes)
    if dt_count >= 5:
        score -= 15
        factors.append({"factor": f"{dt_count} kejadian downtime", "impact": -15})
    elif dt_count >= 2:
        score -= 8
        factors.append({"factor": f"{dt_count} kejadian downtime", "impact": -8})

    score = max(0.0, min(100.0, score))
    if score >= 80:
        status = "healthy"
    elif score >= 60:
        status = "monitor"
    elif score >= 40:
        status = "at_risk"
    else:
        status = "critical"

    # Predict next maintenance window (heuristic)
    next_window = None
    if days_since_pm is None:
        next_window = "Segera (belum ada PM tercatat)"
    elif days_since_pm >= 90:
        next_window = "Dalam 7 hari (overdue)"
    elif days_since_pm >= 60:
        next_window = "Dalam 14-21 hari"
    else:
        target = 90 - days_since_pm
        next_window = f"Dalam {target} hari"

    return {
        "score": round(score, 1),
        "status": status,
        "factors": factors,
        "last_pm_days": days_since_pm,
        "corrective_90d": cm_count,
        "downtime_recent": dt_count,
        "next_maintenance_recommendation": next_window,
    }


async def _gather_machine_data(db, machine_id: str):
    machine = await db[MACHINES_COL].find_one({"id": machine_id}, {"_id": 0})
    logs = await db[LOG_COL].find({"machine_id": machine_id}, {"_id": 0}).sort("performed_at", -1).to_list(length=200)
    cutoff = (datetime.now(timezone.utc) - timedelta(days=90)).isoformat()
    downtimes = await db[DOWNTIME_COL].find(
        {"machine_id": machine_id, "created_at": {"$gte": cutoff}}, {"_id": 0}
    ).to_list(length=200)
    return machine, logs, downtimes


# ═════════════════════════════════════════════════════════════════════
# Endpoints — machines
# ═════════════════════════════════════════════════════════════════════
@router.get("/machines")
async def list_machines(request: Request, limit: int = Query(200, ge=1, le=1000)):
    await require_auth(request)
    db = get_db()

    machines = await db[MACHINES_COL].find().to_list(length=limit)
    machines = [_serialize(m) for m in machines]

    if not machines:
        return {"success": True, "data": []}

    # Bulk fetch logs & downtimes
    m_ids = [m["id"] for m in machines]
    logs_all = await db[LOG_COL].find({"machine_id": {"$in": m_ids}}).to_list(length=5000)
    logs_all = [_serialize(l) for l in logs_all]
    logs_by_machine: dict = {}
    for l in logs_all:
        logs_by_machine.setdefault(l["machine_id"], []).append(l)
    cutoff = (datetime.now(timezone.utc) - timedelta(days=90)).isoformat()
    dts_all = await db[DOWNTIME_COL].find(
        {"machine_id": {"$in": m_ids}, "created_at": {"$gte": cutoff}}
    ).to_list(length=5000)
    dts_all = [_serialize(d) for d in dts_all]
    dts_by_machine: dict = {}
    for d in dts_all:
        dts_by_machine.setdefault(d["machine_id"], []).append(d)

    out = []
    for m in machines:
        h = _machine_health(m, logs_by_machine.get(m["id"], []), dts_by_machine.get(m["id"], []))
        out.append({
            **m,
            "health": h,
            "maintenance_logs_count": len(logs_by_machine.get(m["id"], [])),
        })
    out.sort(key=lambda x: x["health"]["score"])
    return {"success": True, "data": out}


@router.get("/machines/{machine_id}/health")
async def machine_health(request: Request, machine_id: str):
    await require_auth(request)
    db = get_db()
    machine, logs, downtimes = await _gather_machine_data(db, machine_id)
    if not machine:
        raise HTTPException(404, "Machine not found")
    machine = _serialize(machine)
    logs_s = [_serialize(l) for l in logs]
    downtimes_s = [_serialize(d) for d in downtimes]
    health = _machine_health(machine, logs_s, downtimes_s)
    return {
        "success": True,
        "data": {
            "machine": machine,
            "health": health,
            "recent_logs": logs_s[:10],
            "recent_downtimes": downtimes_s[:10],
        },
    }


@router.post("/machines/{machine_id}/predict")
async def predict_with_ai(request: Request, machine_id: str):
    """Generate AI-based prediction & advice for a machine."""
    await require_auth(request)
    db = get_db()
    machine, logs, downtimes = await _gather_machine_data(db, machine_id)
    if not machine:
        raise HTTPException(404, "Machine not found")
    machine = _serialize(machine)
    logs_s = [_serialize(l) for l in logs]
    downtimes_s = [_serialize(d) for d in downtimes]
    health = _machine_health(machine, logs_s, downtimes_s)

    # Try AI advice; if LLM_KEY missing or LLM fails, fall back to heuristic
    advice_text = None
    used_ai = False
    cost_usd = 0.0
    if LLM_KEY:
        try:
            from ai_cost_tracker import tracked_llm_call
            system = (
                "Anda adalah expert maintenance engineer industri garment. "
                "Berikan rekomendasi perawatan mesin yang spesifik, actionable, dalam Bahasa Indonesia. "
                "Format: 3-5 poin singkat (bullet), fokus pada langkah konkret 7-14 hari ke depan."
            )
            recent_logs_text = "\n".join(
                [
                    f"- {l.get('performed_at','?')} | {l.get('maintenance_type','?')} | {l.get('description','-')}"
                    for l in logs_s[:8]
                ]
            ) or "Tidak ada riwayat tercatat"
            recent_dt_text = "\n".join(
                [
                    f"- {d.get('created_at','?')} | {d.get('reason','-')} | durasi {d.get('duration_minutes','?')} mnt"
                    for d in downtimes_s[:5]
                ]
            ) or "Tidak ada downtime tercatat"

            user_msg = (
                f"Mesin: {machine.get('name','?')} (kode {machine.get('code','?')}, tipe {machine.get('type','?')}).\n"
                f"Health score: {health['score']} ({health['status']}).\n"
                f"Last PM: {health['last_pm_days']} hari lalu.\n"
                f"Corrective 90 hari: {health['corrective_90d']}.\n"
                f"Downtime 90 hari: {health['downtime_recent']}.\n\n"
                f"Riwayat maintenance terakhir:\n{recent_logs_text}\n\n"
                f"Downtime terakhir:\n{recent_dt_text}\n\n"
                "Berikan rekomendasi perawatan."
            )
            tracked = await tracked_llm_call(
                feature="predictive_maintenance",
                user_id=getattr(request.state, "user", {}).get("id"),
                model=LLM_MODEL,
                system_message=system,
                user_message=user_msg,
                api_key=LLM_KEY,
                session_id=f"pm-predict-{machine_id}-{uuid.uuid4().hex[:6]}",
            )
            if tracked.over_budget:
                logger.warning(f"PM AI advice skipped (budget): {tracked.budget_warning}")
            elif tracked.success:
                advice_text = tracked.text
                used_ai = True
                cost_usd = tracked.cost_usd
            else:
                logger.warning(f"AI advice failed: {tracked.error}")
        except Exception as e:
            logger.warning(f"AI advice failed, falling back: {e}")
            advice_text = None

    if not advice_text:
        # Fallback heuristic advice
        tips = []
        if health["last_pm_days"] is None or health["last_pm_days"] > 90:
            tips.append("Jadwalkan preventive maintenance dalam 7 hari ke depan.")
        if health["corrective_90d"] >= 2:
            tips.append("Root-cause analysis terhadap pola kerusakan berulang.")
        if health["downtime_recent"] >= 2:
            tips.append("Audit visual pada komponen yang sering downtime + cek alignment.")
        if not tips:
            tips.append("Lanjutkan PM sesuai jadwal — kondisi baik.")
        advice_text = "\n".join(f"• {t}" for t in tips)

    # Save the prediction
    prediction = {
        "id": str(uuid.uuid4()),
        "machine_id": machine_id,
        "machine_name": machine.get("name"),
        "health": health,
        "advice": advice_text,
        "used_ai": used_ai,
        "cost_usd": round(cost_usd, 6) if used_ai else 0,
        "created_at": _now_iso(),
    }
    await db["rahaza_maintenance_predictions"].insert_one(prediction)
    prediction.pop("_id", None)

    return {"success": True, "data": prediction}


# ═════════════════════════════════════════════════════════════════════
# Endpoints — maintenance logs
# ═════════════════════════════════════════════════════════════════════
@router.get("/maintenance-logs")
async def list_logs(
    request: Request,
    machine_id: Optional[str] = Query(None),
    maintenance_type: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=1000),
):
    await require_auth(request)
    db = get_db()
    q: dict = {}
    if machine_id:
        q["machine_id"] = machine_id
    if maintenance_type:
        q["maintenance_type"] = maintenance_type
    logs = await db[LOG_COL].find(q).sort("performed_at", -1).to_list(length=limit)
    return {"success": True, "data": [_serialize(l) for l in logs]}


@router.post("/maintenance-logs")
async def create_log(request: Request, payload: MaintenanceLogIn):
    await require_auth(request)
    db = get_db()
    user = request.state.user
    log = payload.dict()
    log["id"] = str(uuid.uuid4())
    log["performed_at"] = log.get("performed_at") or _now_iso()
    log["created_by"] = user.get("id")
    log["created_at"] = _now_iso()
    # If machine_name not supplied, fetch from machines collection
    if not log.get("machine_name"):
        m = await db[MACHINES_COL].find_one({"id": log["machine_id"]})
        if m:
            log["machine_name"] = m.get("name")
    await db[LOG_COL].insert_one(log)
    log.pop("_id", None)
    return {"success": True, "data": log, "message": "Maintenance log dicatat"}


@router.delete("/maintenance-logs/{log_id}")
async def delete_log(request: Request, log_id: str):
    await require_auth(request)
    db = get_db()
    res = await db[LOG_COL].delete_one({"id": log_id})
    if res.deleted_count == 0:
        raise HTTPException(404, "Log not found")
    return {"success": True, "message": "Log dihapus"}


# ═════════════════════════════════════════════════════════════════════
# Dashboard
# ═════════════════════════════════════════════════════════════════════
@router.get("/dashboard")
async def dashboard(request: Request):
    await require_auth(request)
    db = get_db()
    machines = await db[MACHINES_COL].find().to_list(length=500)
    machines = [_serialize(m) for m in machines]
    if not machines:
        return {
            "success": True,
            "data": {
                "total_machines": 0,
                "healthy": 0,
                "monitor": 0,
                "at_risk": 0,
                "critical": 0,
                "average_score": 0,
                "critical_machines": [],
                "overdue_pm": 0,
            },
        }

    m_ids = [m["id"] for m in machines]
    logs_all = await db[LOG_COL].find({"machine_id": {"$in": m_ids}}).to_list(length=5000)
    logs_all = [_serialize(l) for l in logs_all]
    logs_by_machine: dict = {}
    for l in logs_all:
        logs_by_machine.setdefault(l["machine_id"], []).append(l)
    cutoff = (datetime.now(timezone.utc) - timedelta(days=90)).isoformat()
    dts_all = await db[DOWNTIME_COL].find(
        {"machine_id": {"$in": m_ids}, "created_at": {"$gte": cutoff}}
    ).to_list(length=5000)
    dts_all = [_serialize(d) for d in dts_all]
    dts_by_machine: dict = {}
    for d in dts_all:
        dts_by_machine.setdefault(d["machine_id"], []).append(d)

    counts = {"healthy": 0, "monitor": 0, "at_risk": 0, "critical": 0}
    score_sum = 0.0
    critical_list = []
    overdue_pm = 0
    for m in machines:
        h = _machine_health(m, logs_by_machine.get(m["id"], []), dts_by_machine.get(m["id"], []))
        counts[h["status"]] = counts.get(h["status"], 0) + 1
        score_sum += h["score"]
        if h["last_pm_days"] is None or h["last_pm_days"] > 90:
            overdue_pm += 1
        if h["status"] == "critical":
            critical_list.append(
                {
                    "id": m["id"],
                    "name": m.get("name"),
                    "code": m.get("code"),
                    "score": h["score"],
                    "next_maintenance_recommendation": h["next_maintenance_recommendation"],
                }
            )

    return {
        "success": True,
        "data": {
            "total_machines": len(machines),
            "healthy": counts["healthy"],
            "monitor": counts["monitor"],
            "at_risk": counts["at_risk"],
            "critical": counts["critical"],
            "average_score": round(score_sum / len(machines), 1),
            "critical_machines": critical_list,
            "overdue_pm": overdue_pm,
        },
    }
