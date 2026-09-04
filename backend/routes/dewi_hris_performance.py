"""
CV. Dewi Aditya — Phase 6.1 HRIS Performance Management
  - KPI/OKR cycles (quarterly/yearly)
  - KPI template catalog (sales/quality/attendance/teamwork/innovation)
  - KPI assignments to employees (per cycle)
  - Performance reviews & scoring (self + manager)

Collections:
- dewi_perf_cycles
- dewi_perf_kpis
- dewi_perf_assignments
- dewi_perf_reviews
"""
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel, Field, field_validator

from database import get_db
from auth import require_auth
from utils.helpers import _uid, _now, _clean


router = APIRouter(prefix="/api/dewi/hris/performance", tags=["dewi-hris-performance"])


CYCLE_TYPES = ["quarterly", "half_year", "yearly"]
CYCLE_STATUSES = ["draft", "active", "closed"]
KPI_CATEGORIES = ["sales", "quality", "attendance", "teamwork", "innovation", "productivity", "leadership"]
TARGET_OPERATORS = [">=", "<=", "=", ">", "<"]
ASSIGNMENT_STATUSES = ["assigned", "in_progress", "review", "completed"]
REVIEW_STATUSES = ["draft", "self_submitted", "manager_review", "finalized"]


# ═════════════════════════════════════════════════════════════════════════════
# PYDANTIC MODELS
# ═════════════════════════════════════════════════════════════════════════════

class CycleIn(BaseModel):
    cycle_code: str = Field(..., min_length=2, max_length=30)
    name: str = Field(..., min_length=2)
    period_type: str = "quarterly"
    start_date: str
    end_date: str
    notes: Optional[str] = None
    status: str = "draft"

    @field_validator("period_type")
    @classmethod
    def _validate_period(cls, v):
        if v not in CYCLE_TYPES:
            raise ValueError(f"period_type harus salah satu: {CYCLE_TYPES}")
        return v

    @field_validator("status")
    @classmethod
    def _validate_status(cls, v):
        if v not in CYCLE_STATUSES:
            raise ValueError(f"status harus salah satu: {CYCLE_STATUSES}")
        return v


class CyclePatchIn(BaseModel):
    name: Optional[str] = None
    period_type: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    notes: Optional[str] = None
    status: Optional[str] = None


class KPIIn(BaseModel):
    kpi_code: str = Field(..., min_length=2, max_length=30)
    name: str = Field(..., min_length=2)
    category: str = "productivity"
    description: Optional[str] = None
    measurement: str = Field(default="", description="satuan pengukuran, e.g. '% on-time'")
    target_value: float = 0.0
    target_operator: str = ">="
    weight_default: float = Field(default=20.0, ge=0, le=100)
    is_active: bool = True

    @field_validator("category")
    @classmethod
    def _validate_cat(cls, v):
        if v not in KPI_CATEGORIES:
            raise ValueError(f"category harus salah satu: {KPI_CATEGORIES}")
        return v

    @field_validator("target_operator")
    @classmethod
    def _validate_op(cls, v):
        if v not in TARGET_OPERATORS:
            raise ValueError(f"target_operator harus salah satu: {TARGET_OPERATORS}")
        return v


class KPIPatchIn(BaseModel):
    name: Optional[str] = None
    category: Optional[str] = None
    description: Optional[str] = None
    measurement: Optional[str] = None
    target_value: Optional[float] = None
    target_operator: Optional[str] = None
    weight_default: Optional[float] = Field(default=None, ge=0, le=100)
    is_active: Optional[bool] = None


class AssignmentKPIItem(BaseModel):
    kpi_id: str
    kpi_code: Optional[str] = None
    kpi_name: Optional[str] = None
    category: Optional[str] = None
    weight: float = Field(default=20.0, ge=0, le=100)
    target_value: float = 0.0
    target_operator: str = ">="
    measurement: Optional[str] = None


class AssignmentIn(BaseModel):
    cycle_id: str
    employee_id: str
    manager_id: Optional[str] = None
    kpis: List[AssignmentKPIItem] = Field(default_factory=list)
    notes: Optional[str] = None


class AssignmentPatchIn(BaseModel):
    manager_id: Optional[str] = None
    kpis: Optional[List[AssignmentKPIItem]] = None
    notes: Optional[str] = None
    status: Optional[str] = None
    progress_pct: Optional[float] = Field(default=None, ge=0, le=100)


class ScoreItem(BaseModel):
    kpi_id: str
    actual_value: Optional[float] = None
    rating: float = Field(default=3.0, ge=1, le=5)
    notes: Optional[str] = None


class ReviewSubmitIn(BaseModel):
    actor: str = Field(default="self", description="self | manager")
    scores: List[ScoreItem] = Field(default_factory=list)
    overall_notes: Optional[str] = None


# ═════════════════════════════════════════════════════════════════════════════
# HELPERS
# ═════════════════════════════════════════════════════════════════════════════

async def _get_employee(db, employee_id: str) -> Optional[dict]:
    return await db.rahaza_employees.find_one({"id": employee_id}) or await db.rahaza_employees.find_one({"nik": employee_id})


def _weighted_score(scores: List[dict], assignment_kpis: List[dict]) -> float:
    """Compute weighted final score (1-5 scale) from a list of per-KPI ratings."""
    if not scores or not assignment_kpis:
        return 0.0
    weight_map = {k["kpi_id"]: float(k.get("weight", 0)) for k in assignment_kpis}
    total_weight = sum(weight_map.values()) or 100.0
    total = 0.0
    for s in scores:
        w = weight_map.get(s.get("kpi_id"), 0.0)
        r = float(s.get("rating", 0))
        total += r * (w / total_weight)
    return round(total, 2)


# ═════════════════════════════════════════════════════════════════════════════
# CYCLES
# ═════════════════════════════════════════════════════════════════════════════

@router.get("/cycles")
async def list_cycles(
    status: Optional[str] = None,
    user: dict = Depends(require_auth),
):
    db = get_db()
    q: Dict[str, Any] = {}
    if status and status != "all":
        q["status"] = status
    cursor = db.dewi_perf_cycles.find(q).sort("start_date", -1)
    return [_clean(d) async for d in cursor]


@router.post("/cycles")
async def create_cycle(payload: CycleIn, user: dict = Depends(require_auth)):
    db = get_db()
    if await db.dewi_perf_cycles.find_one({"cycle_code": payload.cycle_code}):
        raise HTTPException(400, f"Cycle code {payload.cycle_code} sudah ada")
    doc = payload.model_dump()
    doc.update({
        "id": _uid(),
        "created_at": _now(),
        "updated_at": _now(),
        "created_by": user.get("name", "System"),
    })
    await db.dewi_perf_cycles.insert_one(doc)
    return _clean(doc)


@router.put("/cycles/{cycle_id}")
async def update_cycle(cycle_id: str, payload: CyclePatchIn, user: dict = Depends(require_auth)):
    db = get_db()
    existing = await db.dewi_perf_cycles.find_one({"id": cycle_id})
    if not existing:
        raise HTTPException(404, "Cycle tidak ditemukan")
    patch = {k: v for k, v in payload.model_dump(exclude_none=True).items()}
    if patch.get("status") and patch["status"] not in CYCLE_STATUSES:
        raise HTTPException(400, f"status harus salah satu: {CYCLE_STATUSES}")
    patch["updated_at"] = _now()
    await db.dewi_perf_cycles.update_one({"id": cycle_id}, {"$set": patch})
    return {"message": "Cycle diperbarui"}


# ═════════════════════════════════════════════════════════════════════════════
# KPI TEMPLATES
# ═════════════════════════════════════════════════════════════════════════════

@router.get("/kpis")
async def list_kpis(
    category: Optional[str] = None,
    is_active: Optional[bool] = None,
    user: dict = Depends(require_auth),
):
    db = get_db()
    q: Dict[str, Any] = {}
    if category:
        q["category"] = category
    if is_active is not None:
        q["is_active"] = is_active
    cursor = db.dewi_perf_kpis.find(q).sort("name", 1)
    return [_clean(d) async for d in cursor]


@router.post("/kpis")
async def create_kpi(payload: KPIIn, user: dict = Depends(require_auth)):
    db = get_db()
    if await db.dewi_perf_kpis.find_one({"kpi_code": payload.kpi_code}):
        raise HTTPException(400, f"KPI code {payload.kpi_code} sudah ada")
    doc = payload.model_dump()
    doc.update({
        "id": _uid(),
        "created_at": _now(),
        "updated_at": _now(),
        "created_by": user.get("name", "System"),
    })
    await db.dewi_perf_kpis.insert_one(doc)
    return _clean(doc)


@router.put("/kpis/{kpi_id}")
async def update_kpi(kpi_id: str, payload: KPIPatchIn, user: dict = Depends(require_auth)):
    db = get_db()
    existing = await db.dewi_perf_kpis.find_one({"id": kpi_id})
    if not existing:
        raise HTTPException(404, "KPI tidak ditemukan")
    patch = {k: v for k, v in payload.model_dump(exclude_none=True).items()}
    if patch.get("category") and patch["category"] not in KPI_CATEGORIES:
        raise HTTPException(400, f"category harus salah satu: {KPI_CATEGORIES}")
    if patch.get("target_operator") and patch["target_operator"] not in TARGET_OPERATORS:
        raise HTTPException(400, f"target_operator harus salah satu: {TARGET_OPERATORS}")
    patch["updated_at"] = _now()
    await db.dewi_perf_kpis.update_one({"id": kpi_id}, {"$set": patch})
    return {"message": "KPI diperbarui"}


# ═════════════════════════════════════════════════════════════════════════════
# ASSIGNMENTS
# ═════════════════════════════════════════════════════════════════════════════

@router.get("/assignments")
async def list_assignments(
    cycle_id: Optional[str] = None,
    employee_id: Optional[str] = None,
    status: Optional[str] = None,
    user: dict = Depends(require_auth),
):
    db = get_db()
    q: Dict[str, Any] = {}
    if cycle_id:
        q["cycle_id"] = cycle_id
    if employee_id:
        q["employee_id"] = employee_id
    if status and status != "all":
        q["status"] = status
    cursor = db.dewi_perf_assignments.find(q).sort("created_at", -1)
    return [_clean(d) async for d in cursor]


@router.get("/assignments/{aid}")
async def get_assignment(aid: str, user: dict = Depends(require_auth)):
    db = get_db()
    d = await db.dewi_perf_assignments.find_one({"id": aid})
    if not d:
        raise HTTPException(404, "Assignment tidak ditemukan")
    return _clean(d)


@router.post("/assignments")
async def create_assignment(payload: AssignmentIn, user: dict = Depends(require_auth)):
    db = get_db()
    cycle = await db.dewi_perf_cycles.find_one({"id": payload.cycle_id})
    if not cycle:
        raise HTTPException(400, "Cycle tidak valid")
    emp = await _get_employee(db, payload.employee_id)
    if not emp:
        raise HTTPException(400, "Employee tidak valid")

    # Enrich each KPI with latest catalog data (single batch fetch instead of N find_one)
    enriched_kpis: List[dict] = []
    total_weight = 0.0
    kpi_ids = [item.kpi_id for item in payload.kpis]
    if kpi_ids:
        kpi_docs = await db.dewi_perf_kpis.find({"id": {"$in": kpi_ids}}).to_list(length=None)
        kpi_by_id = {k["id"]: k for k in kpi_docs}
    else:
        kpi_by_id = {}
    for item in payload.kpis:
        kpi = kpi_by_id.get(item.kpi_id)
        if not kpi:
            raise HTTPException(400, f"KPI {item.kpi_id} tidak ditemukan")
        enriched_kpis.append({
            "kpi_id": item.kpi_id,
            "kpi_code": kpi.get("kpi_code"),
            "kpi_name": kpi.get("name"),
            "category": kpi.get("category"),
            "weight": float(item.weight),
            "target_value": float(item.target_value) if item.target_value is not None else float(kpi.get("target_value", 0)),
            "target_operator": item.target_operator or kpi.get("target_operator", ">="),
            "measurement": item.measurement or kpi.get("measurement", ""),
        })
        total_weight += float(item.weight)

    manager = None
    if payload.manager_id:
        manager = await _get_employee(db, payload.manager_id)

    doc = {
        "id": _uid(),
        "assignment_code": f"PERF-{cycle.get('cycle_code', 'CYC')}-{emp.get('nik', 'EMP')}",
        "cycle_id": payload.cycle_id,
        "cycle_code": cycle.get("cycle_code"),
        "cycle_name": cycle.get("name"),
        "employee_id": emp.get("id"),
        "employee_nik": emp.get("nik"),
        "employee_name": emp.get("name"),
        "department": emp.get("department"),
        "position": emp.get("position"),
        "manager_id": manager.get("id") if manager else None,
        "manager_name": manager.get("name") if manager else None,
        "kpis": enriched_kpis,
        "total_weight": total_weight,
        "status": "assigned",
        "progress_pct": 0.0,
        "notes": payload.notes,
        "created_at": _now(),
        "updated_at": _now(),
        "created_by": user.get("name", "System"),
    }
    await db.dewi_perf_assignments.insert_one(doc)
    return _clean(doc)


@router.put("/assignments/{aid}")
async def update_assignment(aid: str, payload: AssignmentPatchIn, user: dict = Depends(require_auth)):
    db = get_db()
    existing = await db.dewi_perf_assignments.find_one({"id": aid})
    if not existing:
        raise HTTPException(404, "Assignment tidak ditemukan")
    patch: Dict[str, Any] = {k: v for k, v in payload.model_dump(exclude_none=True).items()}
    if "kpis" in patch:
        patch["kpis"] = [k if isinstance(k, dict) else k.model_dump() for k in patch["kpis"]]
        patch["total_weight"] = sum(float(k.get("weight", 0)) for k in patch["kpis"])
    if patch.get("status") and patch["status"] not in ASSIGNMENT_STATUSES:
        raise HTTPException(400, f"status harus salah satu: {ASSIGNMENT_STATUSES}")
    patch["updated_at"] = _now()
    await db.dewi_perf_assignments.update_one({"id": aid}, {"$set": patch})
    return {"message": "Assignment diperbarui"}


# ═════════════════════════════════════════════════════════════════════════════
# REVIEWS
# ═════════════════════════════════════════════════════════════════════════════

@router.get("/reviews")
async def list_reviews(
    cycle_id: Optional[str] = None,
    employee_id: Optional[str] = None,
    status: Optional[str] = None,
    user: dict = Depends(require_auth),
):
    db = get_db()
    q: Dict[str, Any] = {}
    if cycle_id:
        q["cycle_id"] = cycle_id
    if employee_id:
        q["employee_id"] = employee_id
    if status and status != "all":
        q["status"] = status
    cursor = db.dewi_perf_reviews.find(q).sort("created_at", -1)
    return [_clean(d) async for d in cursor]


@router.get("/reviews/{rid}")
async def get_review(rid: str, user: dict = Depends(require_auth)):
    db = get_db()
    d = await db.dewi_perf_reviews.find_one({"id": rid})
    if not d:
        raise HTTPException(404, "Review tidak ditemukan")
    return _clean(d)


@router.post("/reviews")
async def create_or_get_review(assignment_id: str = Query(...), user: dict = Depends(require_auth)):
    """Create a new review draft for an assignment, or return existing."""
    db = get_db()
    existing = await db.dewi_perf_reviews.find_one({"assignment_id": assignment_id})
    if existing:
        return _clean(existing)
    assignment = await db.dewi_perf_assignments.find_one({"id": assignment_id})
    if not assignment:
        raise HTTPException(404, "Assignment tidak ditemukan")
    doc = {
        "id": _uid(),
        "review_code": f"REV-{assignment.get('assignment_code', 'PERF')}",
        "assignment_id": assignment_id,
        "cycle_id": assignment.get("cycle_id"),
        "cycle_code": assignment.get("cycle_code"),
        "employee_id": assignment.get("employee_id"),
        "employee_nik": assignment.get("employee_nik"),
        "employee_name": assignment.get("employee_name"),
        "department": assignment.get("department"),
        "manager_id": assignment.get("manager_id"),
        "manager_name": assignment.get("manager_name"),
        "self_scores": [],
        "self_overall_notes": None,
        "self_submitted_at": None,
        "manager_scores": [],
        "manager_overall_notes": None,
        "manager_submitted_at": None,
        "final_score": 0.0,
        "final_rating": 0.0,
        "status": "draft",
        "created_at": _now(),
        "updated_at": _now(),
        "created_by": user.get("name", "System"),
    }
    await db.dewi_perf_reviews.insert_one(doc)
    return _clean(doc)


@router.put("/reviews/{rid}/submit")
async def submit_review(rid: str, payload: ReviewSubmitIn, user: dict = Depends(require_auth)):
    db = get_db()
    review = await db.dewi_perf_reviews.find_one({"id": rid})
    if not review:
        raise HTTPException(404, "Review tidak ditemukan")
    if payload.actor not in ("self", "manager"):
        raise HTTPException(400, "actor harus 'self' atau 'manager'")

    assignment = await db.dewi_perf_assignments.find_one({"id": review.get("assignment_id")})
    assignment_kpis = (assignment or {}).get("kpis", [])

    patch: Dict[str, Any] = {"updated_at": _now()}
    scores_as_dict = [s.model_dump() for s in payload.scores]

    raise_proposal_created = False

    if payload.actor == "self":
        patch["self_scores"] = scores_as_dict
        patch["self_overall_notes"] = payload.overall_notes
        patch["self_submitted_at"] = _now()
        patch["status"] = "self_submitted"
    else:  # manager
        patch["manager_scores"] = scores_as_dict
        patch["manager_overall_notes"] = payload.overall_notes
        patch["manager_submitted_at"] = _now()
        # Final score = manager score weighted
        final_score = _weighted_score(scores_as_dict, assignment_kpis)
        patch["final_score"] = final_score
        patch["final_rating"] = final_score
        patch["status"] = "finalized"
        # Mark assignment as completed
        if assignment:
            await db.dewi_perf_assignments.update_one(
                {"id": assignment["id"]},
                {"$set": {"status": "completed", "progress_pct": 100.0, "updated_at": _now()}},
            )

        # ── P2: Auto-create raise proposal for high performer (score ≥ 4.0) ──
        if final_score >= 4.0 and assignment:
            raise_pct = 5.0 if final_score >= 4.5 else 3.0
            emp_id = assignment.get("employee_id")
            emp = await db.rahaza_employees.find_one({"id": emp_id}, {"_id": 0}) if emp_id else None
            profile = await db.rahaza_payroll_profiles.find_one(
                {"employee_id": emp_id, "active": True}, {"_id": 0}
            ) if emp_id else None

            current_base = float((profile or {}).get("base_rate", 0))
            if current_base > 0 and emp_id:
                # Idempotency: skip if active performance_raise exists for same review
                existing_adj = await db.rahaza_salary_adjustments.find_one({
                    "employee_id": emp_id,
                    "source_review_id": rid,
                    "adjustment_type": "performance_raise",
                    "status": {"$nin": ["rejected", "cancelled"]},
                })
                if not existing_adj:
                    raise_amount = round(current_base * (raise_pct / 100))
                    proposed_base = current_base + raise_amount
                    manager_id = (emp or {}).get("manager_id")
                    cycle = await db.dewi_perf_cycles.find_one(
                        {"id": assignment.get("cycle_id")}, {"_id": 0, "name": 1}
                    )
                    adj_doc = {
                        "id": _uid(),
                        "employee_id": emp_id,
                        "employee_name": (emp or {}).get("name", assignment.get("employee_name", "-")),
                        "employee_code": (emp or {}).get("employee_code", "-"),
                        "manager_id": manager_id,
                        "manager_name": (emp or {}).get("manager_name", ""),
                        "adjustment_type": "performance_raise",
                        "source_review_id": rid,
                        "performance_cycle_id": assignment.get("cycle_id"),
                        "performance_cycle_name": (cycle or {}).get("name", ""),
                        "performance_final_score": final_score,
                        "current_base": current_base,
                        "proposed_base": float(proposed_base),
                        "raise_amount": float(raise_amount),
                        "raise_pct": raise_pct,
                        "reason": (
                            f"Annual Performance Score {final_score:.1f}/5.0 "
                            f"({'Outstanding' if final_score >= 4.5 else 'Exceeds Expectations'}) "
                            f"— Siklus: {(cycle or {}).get('name', '')}"
                        ),
                        "status": "pending_manager" if manager_id else "pending_hr",
                        "created_at": _now(),
                        "created_by": user.get("id", ""),
                        "notes": "",
                        "approval_notes": "",
                    }
                    await db.rahaza_salary_adjustments.insert_one(adj_doc)
                    raise_proposal_created = True

    await db.dewi_perf_reviews.update_one({"id": rid}, {"$set": patch})
    return {
        "message": f"Review {payload.actor} berhasil di-submit",
        "final_score": patch.get("final_score", review.get("final_score", 0)),
        "raise_proposal_created": raise_proposal_created,
        "raise_pct": (5.0 if patch.get("final_score", 0) >= 4.5 else 3.0) if raise_proposal_created else 0,
    }


# ═════════════════════════════════════════════════════════════════════════════
# SUMMARY
# ═════════════════════════════════════════════════════════════════════════════

@router.get("/summary")
async def performance_summary(cycle_id: Optional[str] = None, user: dict = Depends(require_auth)):
    db = get_db()
    cycle_filter: Dict[str, Any] = {"cycle_id": cycle_id} if cycle_id else {}

    active_cycle = await db.dewi_perf_cycles.find_one({"status": "active"})
    total_cycles = await db.dewi_perf_cycles.count_documents({})
    total_kpis = await db.dewi_perf_kpis.count_documents({"is_active": True})
    total_assignments = await db.dewi_perf_assignments.count_documents(cycle_filter)
    completed_assignments = await db.dewi_perf_assignments.count_documents({**cycle_filter, "status": "completed"})
    in_progress = await db.dewi_perf_assignments.count_documents({**cycle_filter, "status": {"$in": ["assigned", "in_progress", "review"]}})
    total_reviews = await db.dewi_perf_reviews.count_documents(cycle_filter)
    finalized_reviews = await db.dewi_perf_reviews.count_documents({**cycle_filter, "status": "finalized"})

    # Average final score (finalized reviews)
    pipeline = [{"$match": {**cycle_filter, "status": "finalized"}}, {"$group": {"_id": None, "avg_score": {"$avg": "$final_score"}}}]
    avg_doc = await db.dewi_perf_reviews.aggregate(pipeline).to_list(length=1)
    avg_score = round(avg_doc[0]["avg_score"], 2) if avg_doc else 0.0

    return {
        "active_cycle": _clean(active_cycle) if active_cycle else None,
        "total_cycles": total_cycles,
        "total_kpis": total_kpis,
        "total_assignments": total_assignments,
        "completed_assignments": completed_assignments,
        "in_progress": in_progress,
        "total_reviews": total_reviews,
        "finalized_reviews": finalized_reviews,
        "avg_final_score": avg_score,
    }


# ═════════════════════════════════════════════════════════════════════════════
# SEED (idempotent)
# ═════════════════════════════════════════════════════════════════════════════

@router.post("/seed-demo")
async def seed_performance_demo(user: dict = Depends(require_auth)):
    """Seed 1 active cycle + 5 KPI templates + 8 assignments + 3 reviews (idempotent)."""
    if user.get("role") not in ("superadmin", "admin"):
        raise HTTPException(403, "Hanya admin yang bisa seed")

    db = get_db()
    now = _now()
    counts = {"cycles": 0, "kpis": 0, "assignments": 0, "reviews": 0}
    user_name = user.get("name", "System")

    # --- Cycle ---
    cycle = await db.dewi_perf_cycles.find_one({"cycle_code": "Q2-2026"})
    if not cycle:
        cycle = {
            "id": _uid(), "cycle_code": "Q2-2026", "name": "Quarter 2 — 2026 (Apr-Jun)",
            "period_type": "quarterly", "start_date": "2026-04-01", "end_date": "2026-06-30",
            "status": "active", "notes": "Cycle penilaian kinerja Q2 2026",
            "created_at": now, "updated_at": now, "created_by": user_name,
        }
        await db.dewi_perf_cycles.insert_one(cycle)
        counts["cycles"] += 1

    # Also seed Q1 (closed) for historical context
    if not await db.dewi_perf_cycles.find_one({"cycle_code": "Q1-2026"}):
        await db.dewi_perf_cycles.insert_one({
            "id": _uid(), "cycle_code": "Q1-2026", "name": "Quarter 1 — 2026 (Jan-Mar)",
            "period_type": "quarterly", "start_date": "2026-01-01", "end_date": "2026-03-31",
            "status": "closed", "notes": "Cycle Q1 sudah closed",
            "created_at": now, "updated_at": now, "created_by": user_name,
        })
        counts["cycles"] += 1

    # --- KPI templates ---
    kpi_specs = [
        ("KPI-PROD-01", "Pencapaian Target Produksi", "productivity",
         "% pencapaian target produksi bulanan", "%", 95.0, ">=", 25.0),
        ("KPI-QLTY-02", "Defect Rate", "quality",
         "% cacat terhadap total produksi", "%", 2.0, "<=", 20.0),
        ("KPI-ATND-03", "Kehadiran", "attendance",
         "% kehadiran terhadap hari kerja", "%", 95.0, ">=", 15.0),
        ("KPI-TEAM-04", "Kerja Sama Tim", "teamwork",
         "Skor 360 kerja sama & komunikasi (1-5)", "score", 4.0, ">=", 20.0),
        ("KPI-INOV-05", "Inovasi & Improvement", "innovation",
         "Jumlah ide/improvement diterapkan per kuartal", "count", 2.0, ">=", 10.0),
        ("KPI-LEAD-06", "Kepemimpinan (Supervisor+)", "leadership",
         "Skor kepemimpinan dari tim (1-5)", "score", 4.0, ">=", 10.0),
    ]
    kpi_id_map: Dict[str, str] = {}
    # Single $in query for all existing kpi_codes
    codes = [s[0] for s in kpi_specs]
    existing_kpis = await db.dewi_perf_kpis.find(
        {"kpi_code": {"$in": codes}}
    ).to_list(length=None)
    by_code = {k["kpi_code"]: k for k in existing_kpis}
    for code, name, cat, desc, meas, target, op, weight in kpi_specs:
        existing = by_code.get(code)
        if existing:
            kpi_id_map[code] = existing["id"]
            continue
        kid = _uid()
        await db.dewi_perf_kpis.insert_one({
            "id": kid, "kpi_code": code, "name": name, "category": cat,
            "description": desc, "measurement": meas, "target_value": target,
            "target_operator": op, "weight_default": weight, "is_active": True,
            "created_at": now, "updated_at": now, "created_by": user_name,
        })
        kpi_id_map[code] = kid
        counts["kpis"] += 1

    # --- Assignments (8 employees, non-leadership KPIs for operator/staff, all for sup) ---
    if await db.dewi_perf_assignments.count_documents({"cycle_id": cycle["id"]}) < 5:
        emps = await db.rahaza_employees.find({}).limit(10).to_list(length=10)
        if emps:
            manager = next((e for e in emps if "Supervisor" in (e.get("position") or "")), emps[0])

            def kpi_item(code: str, weight: float, target: Optional[float] = None) -> dict:
                kpi_doc = next((s for s in kpi_specs if s[0] == code), None)
                return {
                    "kpi_id": kpi_id_map.get(code, ""),
                    "kpi_code": code,
                    "kpi_name": kpi_doc[1] if kpi_doc else code,
                    "category": kpi_doc[2] if kpi_doc else "productivity",
                    "weight": weight,
                    "target_value": target if target is not None else (kpi_doc[5] if kpi_doc else 0.0),
                    "target_operator": kpi_doc[6] if kpi_doc else ">=",
                    "measurement": kpi_doc[4] if kpi_doc else "",
                }

            default_kpis = [
                kpi_item("KPI-PROD-01", 30.0),
                kpi_item("KPI-QLTY-02", 25.0),
                kpi_item("KPI-ATND-03", 20.0),
                kpi_item("KPI-TEAM-04", 25.0),
            ]
            sup_kpis = default_kpis + [kpi_item("KPI-LEAD-06", 15.0), kpi_item("KPI-INOV-05", 10.0)]

            statuses = ["assigned", "in_progress", "in_progress", "review", "assigned", "in_progress", "review", "assigned"]
            progress_pcts = [0, 40, 55, 85, 10, 60, 90, 20]

            # Prefetch existing assignments in single query
            emp_ids_to_check = [e["id"] for e in emps[:8]]
            existing_assignments = await db.dewi_perf_assignments.find(
                {"cycle_id": cycle["id"], "employee_id": {"$in": emp_ids_to_check}}
            ).to_list(length=None)
            existing_emp_ids = {a["employee_id"] for a in existing_assignments}

            for i, emp in enumerate(emps[:8]):
                if emp["id"] in existing_emp_ids:
                    continue
                is_sup = "Supervisor" in (emp.get("position") or "")
                kpis = sup_kpis if is_sup else default_kpis
                # Normalize weights to sum 100
                total_w = sum(k["weight"] for k in kpis)
                kpis = [{**k, "weight": round(k["weight"] * 100 / total_w, 1)} for k in kpis]

                doc = {
                    "id": _uid(),
                    "assignment_code": f"PERF-Q2-2026-{emp.get('nik', 'EMP')}",
                    "cycle_id": cycle["id"], "cycle_code": "Q2-2026", "cycle_name": cycle["name"],
                    "employee_id": emp["id"], "employee_nik": emp.get("nik"),
                    "employee_name": emp.get("name"),
                    "department": emp.get("department"), "position": emp.get("position"),
                    "manager_id": manager.get("id") if manager.get("id") != emp["id"] else None,
                    "manager_name": manager.get("name") if manager.get("id") != emp["id"] else None,
                    "kpis": kpis, "total_weight": 100.0,
                    "status": statuses[i], "progress_pct": float(progress_pcts[i]),
                    "notes": "Assignment demo seed Q2 2026",
                    "created_at": now, "updated_at": now, "created_by": user_name,
                }
                await db.dewi_perf_assignments.insert_one(doc)
                counts["assignments"] += 1

    # --- Reviews (3 in-progress: 1 self-submitted, 1 manager_review, 1 finalized) ---
    if await db.dewi_perf_reviews.count_documents({"cycle_id": cycle["id"]}) < 2:
        assignments = await db.dewi_perf_assignments.find(
            {"cycle_id": cycle["id"], "status": {"$in": ["review", "in_progress"]}}
        ).limit(3).to_list(length=3)

        def demo_self_scores(a):
            return [
                {"kpi_id": k["kpi_id"], "actual_value": k.get("target_value", 0) * 0.95,
                 "rating": 4.0 - (i * 0.1), "notes": "Self-assessment"}
                for i, k in enumerate(a.get("kpis", []))
            ]

        def demo_mgr_scores(a):
            return [
                {"kpi_id": k["kpi_id"], "actual_value": k.get("target_value", 0) * 0.90,
                 "rating": 3.8 - (i * 0.15), "notes": "Perlu peningkatan di area ini"}
                for i, k in enumerate(a.get("kpis", []))
            ]

        # Prefetch existing reviews per assignment in single query
        a_ids = [a["id"] for a in assignments]
        existing_reviews = await db.dewi_perf_reviews.find(
            {"assignment_id": {"$in": a_ids}}
        ).to_list(length=None)
        reviewed_aids = {r["assignment_id"] for r in existing_reviews}

        for idx, a in enumerate(assignments):
            if a["id"] in reviewed_aids:
                continue
            rid = _uid()
            status = ["self_submitted", "manager_review", "finalized"][idx % 3]
            self_scores = demo_self_scores(a)
            mgr_scores = demo_mgr_scores(a) if status in ("manager_review", "finalized") else []
            final_score = _weighted_score(mgr_scores, a.get("kpis", [])) if mgr_scores else 0.0

            await db.dewi_perf_reviews.insert_one({
                "id": rid,
                "review_code": f"REV-{a.get('assignment_code', 'PERF')}",
                "assignment_id": a["id"], "cycle_id": a["cycle_id"], "cycle_code": a.get("cycle_code"),
                "employee_id": a["employee_id"], "employee_nik": a.get("employee_nik"),
                "employee_name": a.get("employee_name"), "department": a.get("department"),
                "manager_id": a.get("manager_id"), "manager_name": a.get("manager_name"),
                "self_scores": self_scores, "self_overall_notes": "Saya sudah berusaha maksimal.",
                "self_submitted_at": now,
                "manager_scores": mgr_scores,
                "manager_overall_notes": "Kinerja baik dengan beberapa catatan improvement." if mgr_scores else None,
                "manager_submitted_at": now if mgr_scores else None,
                "final_score": final_score,
                "final_rating": final_score,
                "status": status,
                "created_at": now, "updated_at": now, "created_by": user_name,
            })
            counts["reviews"] += 1

    return {"ok": True, "message": "Performance Management demo seeded", "counts": counts}
