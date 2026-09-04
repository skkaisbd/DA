"""
Session 18 — P2-3: Strategic OKR Tracker (Manajemen)

Features:
- CRUD Objectives (quarterly/annual)
- CRUD Key Results (auto-calculated progress per objective)
- Owner / Department scoping
- Dashboard with overall company OKR health
- Status: on_track / at_risk / off_track auto-classified

Endpoints (prefix: /api/management/okr)
- GET    /objectives                       — list (filters: period, owner, status, department)
- POST   /objectives                       — create objective
- GET    /objectives/{id}                  — fetch single with key results
- PATCH  /objectives/{id}                  — update
- DELETE /objectives/{id}                  — soft delete (archived)
- POST   /objectives/{id}/key-results      — add KR
- PATCH  /key-results/{id}                 — update KR (current_value, status)
- DELETE /key-results/{id}                 — delete KR
- GET    /dashboard                        — high-level summary
- GET    /periods                          — list distinct periods
"""
import uuid
import logging
from datetime import datetime, timezone
from typing import Optional, List
from fastapi import APIRouter, Request, Query, HTTPException
from pydantic import BaseModel, Field
from database import get_db
from auth import require_auth

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/management/okr", tags=["okr"])

OBJ_COL = "rahaza_okr_objectives"
KR_COL = "rahaza_okr_key_results"


# ═════════════════════════════════════════════════════════════════════
# Models
# ═════════════════════════════════════════════════════════════════════
class KeyResultIn(BaseModel):
    title: str
    metric_type: str = Field("number")  # number | percentage | currency | binary
    target_value: float
    current_value: float = 0
    unit: Optional[str] = None  # %, IDR, pcs, dll
    notes: Optional[str] = None


class ObjectiveIn(BaseModel):
    title: str
    description: Optional[str] = None
    period: str  # e.g. 2026-Q1, 2026, 2026-H1
    department: Optional[str] = None
    owner_id: Optional[str] = None
    owner_name: Optional[str] = None
    priority: str = Field("medium")  # low/medium/high/critical
    key_results: List[KeyResultIn] = []


class ObjectivePatch(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    period: Optional[str] = None
    department: Optional[str] = None
    owner_id: Optional[str] = None
    owner_name: Optional[str] = None
    priority: Optional[str] = None
    status: Optional[str] = None  # active/completed/archived


class KeyResultPatch(BaseModel):
    title: Optional[str] = None
    metric_type: Optional[str] = None
    target_value: Optional[float] = None
    current_value: Optional[float] = None
    unit: Optional[str] = None
    notes: Optional[str] = None
    status: Optional[str] = None


def _now():
    return datetime.now(timezone.utc).isoformat()


def _serialize(obj):
    if isinstance(obj, dict):
        obj.pop("_id", None)
        return {k: _serialize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_serialize(i) for i in obj]
    return obj


def _kr_progress(kr: dict) -> float:
    """Return progress 0..100 for a KR."""
    try:
        target = float(kr.get("target_value", 0) or 0)
        current = float(kr.get("current_value", 0) or 0)
        if target <= 0:
            # Binary completion
            return 100.0 if current > 0 else 0.0
        return min(100.0, max(0.0, (current / target) * 100.0))
    except Exception:
        return 0.0


def _objective_progress(krs: List[dict]) -> float:
    if not krs:
        return 0.0
    return sum(_kr_progress(kr) for kr in krs) / len(krs)


def _objective_health(progress: float, status: str) -> str:
    if status == "completed":
        return "completed"
    if status == "archived":
        return "archived"
    if progress >= 70:
        return "on_track"
    if progress >= 40:
        return "at_risk"
    return "off_track"


# ═════════════════════════════════════════════════════════════════════
# Periods
# ═════════════════════════════════════════════════════════════════════
@router.get("/periods")
async def list_periods(request: Request):
    await require_auth(request)
    db = get_db()
    periods = await db[OBJ_COL].distinct("period")
    periods = sorted([p for p in periods if p], reverse=True)
    return {"success": True, "data": periods}


# ═════════════════════════════════════════════════════════════════════
# Objectives
# ═════════════════════════════════════════════════════════════════════
@router.get("/objectives")
async def list_objectives(
    request: Request,
    period: Optional[str] = Query(None),
    department: Optional[str] = Query(None),
    owner_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    include_key_results: bool = Query(True),
    limit: int = Query(200, ge=1, le=1000),
):
    await require_auth(request)
    db = get_db()
    q = {}
    if period:
        q["period"] = period
    if department:
        q["department"] = department
    if owner_id:
        q["owner_id"] = owner_id
    if status:
        q["status"] = status
    else:
        q["status"] = {"$ne": "archived"}

    objs = await db[OBJ_COL].find(q).sort("created_at", -1).to_list(length=limit)
    objs = [_serialize(o) for o in objs]

    if include_key_results and objs:
        obj_ids = [o["id"] for o in objs]
        krs = await db[KR_COL].find({"objective_id": {"$in": obj_ids}}).to_list(length=2000)
        krs = [_serialize(k) for k in krs]
        by_obj: dict = {}
        for k in krs:
            by_obj.setdefault(k["objective_id"], []).append(k)
        for o in objs:
            o_krs = by_obj.get(o["id"], [])
            o["key_results"] = o_krs
            o["progress"] = round(_objective_progress(o_krs), 1)
            o["health"] = _objective_health(o["progress"], o.get("status", "active"))
            o["key_results_count"] = len(o_krs)
    return {"success": True, "data": objs}


@router.post("/objectives")
async def create_objective(request: Request, payload: ObjectiveIn):
    await require_auth(request)
    db = get_db()
    user = request.state.user
    if user.get("role") not in ["superadmin", "admin", "manager", "owner"]:
        raise HTTPException(403, "Unauthorized")

    obj = payload.dict(exclude={"key_results"})
    obj["id"] = str(uuid.uuid4())
    obj["status"] = "active"
    obj["created_by"] = user.get("id")
    obj["created_at"] = _now()
    obj["updated_at"] = _now()
    await db[OBJ_COL].insert_one(obj)
    obj.pop("_id", None)

    krs_created = []
    for kr in payload.key_results:
        kr_doc = kr.dict()
        kr_doc["id"] = str(uuid.uuid4())
        kr_doc["objective_id"] = obj["id"]
        kr_doc["status"] = "active"
        kr_doc["created_at"] = _now()
        kr_doc["updated_at"] = _now()
        await db[KR_COL].insert_one(kr_doc)
        kr_doc.pop("_id", None)
        krs_created.append(kr_doc)

    obj["key_results"] = krs_created
    obj["progress"] = round(_objective_progress(krs_created), 1)
    obj["health"] = _objective_health(obj["progress"], obj["status"])

    return {"success": True, "data": obj, "message": "Objective dibuat"}


@router.get("/objectives/{obj_id}")
async def get_objective(request: Request, obj_id: str):
    await require_auth(request)
    db = get_db()
    obj = await db[OBJ_COL].find_one({"id": obj_id})
    if not obj:
        raise HTTPException(404, "Objective not found")
    obj = _serialize(obj)
    krs = await db[KR_COL].find({"objective_id": obj_id}).sort("created_at", 1).to_list(length=200)
    krs = [_serialize(k) for k in krs]
    obj["key_results"] = krs
    obj["progress"] = round(_objective_progress(krs), 1)
    obj["health"] = _objective_health(obj["progress"], obj.get("status", "active"))
    return {"success": True, "data": obj}


@router.patch("/objectives/{obj_id}")
async def update_objective(request: Request, obj_id: str, payload: ObjectivePatch):
    await require_auth(request)
    db = get_db()
    update = {k: v for k, v in payload.dict().items() if v is not None}
    if not update:
        raise HTTPException(400, "Tidak ada perubahan")
    update["updated_at"] = _now()
    res = await db[OBJ_COL].update_one({"id": obj_id}, {"$set": update})
    if res.matched_count == 0:
        raise HTTPException(404, "Objective not found")
    return {"success": True, "message": "Objective diperbarui"}


@router.delete("/objectives/{obj_id}")
async def delete_objective(request: Request, obj_id: str):
    await require_auth(request)
    db = get_db()
    user = request.state.user
    if user.get("role") not in ["superadmin", "admin", "manager", "owner"]:
        raise HTTPException(403, "Unauthorized")
    res = await db[OBJ_COL].update_one(
        {"id": obj_id}, {"$set": {"status": "archived", "updated_at": _now()}}
    )
    if res.matched_count == 0:
        raise HTTPException(404, "Objective not found")
    return {"success": True, "message": "Objective di-archive"}


# ═════════════════════════════════════════════════════════════════════
# Key Results
# ═════════════════════════════════════════════════════════════════════
@router.post("/objectives/{obj_id}/key-results")
async def add_key_result(request: Request, obj_id: str, payload: KeyResultIn):
    await require_auth(request)
    db = get_db()
    obj = await db[OBJ_COL].find_one({"id": obj_id})
    if not obj:
        raise HTTPException(404, "Objective not found")
    kr = payload.dict()
    kr["id"] = str(uuid.uuid4())
    kr["objective_id"] = obj_id
    kr["status"] = "active"
    kr["created_at"] = _now()
    kr["updated_at"] = _now()
    await db[KR_COL].insert_one(kr)
    kr.pop("_id", None)
    return {"success": True, "data": kr, "message": "Key Result ditambahkan"}


@router.patch("/key-results/{kr_id}")
async def update_key_result(request: Request, kr_id: str, payload: KeyResultPatch):
    await require_auth(request)
    db = get_db()
    update = {k: v for k, v in payload.dict().items() if v is not None}
    if not update:
        raise HTTPException(400, "Tidak ada perubahan")
    update["updated_at"] = _now()
    res = await db[KR_COL].update_one({"id": kr_id}, {"$set": update})
    if res.matched_count == 0:
        raise HTTPException(404, "Key result not found")
    return {"success": True, "message": "Key Result diperbarui"}


@router.delete("/key-results/{kr_id}")
async def delete_key_result(request: Request, kr_id: str):
    await require_auth(request)
    db = get_db()
    res = await db[KR_COL].delete_one({"id": kr_id})
    if res.deleted_count == 0:
        raise HTTPException(404, "Key result not found")
    return {"success": True, "message": "Key Result dihapus"}


# ═════════════════════════════════════════════════════════════════════
# Dashboard
# ═════════════════════════════════════════════════════════════════════
@router.get("/dashboard")
async def okr_dashboard(request: Request, period: Optional[str] = Query(None)):
    await require_auth(request)
    db = get_db()

    q = {"status": {"$ne": "archived"}}
    if period:
        q["period"] = period

    objs = await db[OBJ_COL].find(q).to_list(length=500)
    objs = [_serialize(o) for o in objs]

    if not objs:
        return {
            "success": True,
            "data": {
                "total_objectives": 0,
                "on_track": 0,
                "at_risk": 0,
                "off_track": 0,
                "completed": 0,
                "average_progress": 0,
                "by_department": [],
                "top_objectives": [],
            },
        }

    obj_ids = [o["id"] for o in objs]
    krs = await db[KR_COL].find({"objective_id": {"$in": obj_ids}}).to_list(length=5000)
    krs = [_serialize(k) for k in krs]
    by_obj: dict = {}
    for k in krs:
        by_obj.setdefault(k["objective_id"], []).append(k)

    on_track = at_risk = off_track = completed_count = 0
    total_progress = 0.0
    dept_stats: dict = {}
    obj_with_progress = []
    for o in objs:
        o_krs = by_obj.get(o["id"], [])
        progress = _objective_progress(o_krs)
        health = _objective_health(progress, o.get("status", "active"))
        if health == "on_track":
            on_track += 1
        elif health == "at_risk":
            at_risk += 1
        elif health == "off_track":
            off_track += 1
        elif health == "completed":
            completed_count += 1
        total_progress += progress
        dept = o.get("department") or "Other"
        ds = dept_stats.setdefault(
            dept, {"department": dept, "total": 0, "progress_sum": 0.0, "critical": 0}
        )
        ds["total"] += 1
        ds["progress_sum"] += progress
        if o.get("priority") == "critical":
            ds["critical"] += 1
        obj_with_progress.append(
            {
                "id": o["id"],
                "title": o["title"],
                "owner_name": o.get("owner_name"),
                "period": o.get("period"),
                "department": o.get("department"),
                "priority": o.get("priority"),
                "progress": round(progress, 1),
                "health": health,
                "key_results_count": len(o_krs),
            }
        )

    by_department = []
    for ds in dept_stats.values():
        avg = ds["progress_sum"] / ds["total"] if ds["total"] else 0
        by_department.append(
            {
                "department": ds["department"],
                "total": ds["total"],
                "average_progress": round(avg, 1),
                "critical_count": ds["critical"],
            }
        )
    by_department.sort(key=lambda d: -d["total"])

    obj_with_progress.sort(key=lambda o: -o["progress"])
    top_objectives = obj_with_progress[:5]

    return {
        "success": True,
        "data": {
            "total_objectives": len(objs),
            "on_track": on_track,
            "at_risk": at_risk,
            "off_track": off_track,
            "completed": completed_count,
            "average_progress": round(total_progress / len(objs), 1),
            "by_department": by_department,
            "top_objectives": top_objectives,
            "all_objectives": obj_with_progress,
        },
    }
