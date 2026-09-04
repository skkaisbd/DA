# ruff: noqa: F401
"""
dewi_kpi_gamification.py — Gamification System
Extracted from dewi_kpi.py (2729 LOC monolith)

Refactored: Session #11.19 Final - CAREFUL APPROACH
"""
from fastapi import APIRouter, Request, HTTPException, Query
from database import get_db
from auth import require_auth, serialize_doc, log_activity
from routes.dewi_kpi_shared import (
    _uid, _now, _s, _grade,
    _require_hr, _get_linked_employee,
    _calc_section_score, _calc_attitude_score, _calc_absensi_score,
    DEFAULT_QUESTIONS,
    BADGE_DEFS, _calculate_and_award_badges,
)
import uuid
import logging
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/dewi/kpi", tags=["dewi-kpi-gamification"])

@router.get("/gamification/summary")
async def gamification_summary(request: Request):
    """Ringkasan gamification untuk HR dashboard."""
    await require_auth(request)
    db = get_db()

    total_badges = await db.da_kpi_badges.count_documents({})
    badge_dist_cursor = db.da_kpi_badges.aggregate([
        {"$group": {"_id": "$badge_type", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}}
    ])
    badge_dist = [doc async for doc in badge_dist_cursor]
    badge_dist_enriched = [
        {
            "badge_type": d["_id"],
            "count": d["count"],
            "badge_emoji": BADGE_DEFS.get(d["_id"], {}).get("emoji", ""),
            "badge_label": BADGE_DEFS.get(d["_id"], {}).get("label", d["_id"]),
            "badge_color": BADGE_DEFS.get(d["_id"], {}).get("color", "#888"),
        }
        for d in badge_dist
    ]

    # Top badge earners
    top_earner_cursor = db.da_kpi_badges.aggregate([
        {"$group": {"_id": "$employee_id", "count": {"$sum": 1},
                    "name": {"$first": "$employee_name"},
                    "code": {"$first": "$employee_code"}}},
        {"$sort": {"count": -1}},
        {"$limit": 5}
    ])
    top_earners = [
        {"employee_id": d["_id"], "employee_name": d["name"],
         "employee_code": d["code"], "badge_count": d["count"]}
        async for d in top_earner_cursor
    ]

    # Recent badges (last 10)
    recent = await db.da_kpi_badges.find({}, {"_id": 0}).sort("earned_at", -1).to_list(10)
    recent_enriched = []
    for b in recent:
        btype = b.get("badge_type", "")
        bdef = BADGE_DEFS.get(btype, {})
        recent_enriched.append({
            **_s(b),
            "badge_color": bdef.get("color", "#888"),
            "badge_desc": bdef.get("desc", ""),
        })

    return {
        "ok": True,
        "total_badges_awarded": total_badges,
        "badge_distribution": badge_dist_enriched,
        "top_earners": top_earners,
        "recent_badges": recent_enriched,
        "badge_types_available": len(BADGE_DEFS),
    }


@router.get("/badges")
async def get_badge_catalog(request: Request):
    """Daftar semua tipe badge yang tersedia."""
    await require_auth(request)
    return {
        "ok": True,
        "badges": [
            {"badge_type": k, **v}
            for k, v in BADGE_DEFS.items()
        ]
    }


@router.post("/gamification/seed-demo")
async def seed_demo_gamification(request: Request):
    """
    Seed demo KPI periods + results + badges untuk testing gamification.
    Hanya bisa dijalankan jika belum ada data periods (idempotent).
    """
    user = await require_auth(request)
    db = get_db()

    existing = await db.da_kpi_periods.count_documents({})
    if existing > 0:
        # Recalculate badges from existing data
        periods = await db.da_kpi_periods.find(
            {"status": {"$in": ["finalized", "closed"]}}, {"_id": 0, "id": 1, "period_id": 1}
        ).to_list(500)
        total_badges = 0
        for p in periods:
            pid = p.get("period_id") or p.get("id")
            res = await _calculate_and_award_badges(db, pid)
            total_badges += res.get("awarded", 0)
        return {"ok": True, "message": f"Badges recalculated ({total_badges} awarded). Data sudah ada.", "seeded": False}

    # Get employees
    emps = await db.rahaza_employees.find({}, {"_id": 0, "id": 1, "name": 1, "employee_code": 1, "department": 1}).to_list(500)
    if not emps:
        raise HTTPException(400, "Seed karyawan dulu (endpoint: /api/rahaza/hr-seed/run)")

    now = datetime.now(timezone.utc)
    created_periods = []
    created_results = []

    # Create 3 demo periods
    periods_data = [
        {"title": "KPI Q1 2025", "month": "2025-03"},
        {"title": "KPI Q2 2025", "month": "2025-06"},
        {"title": "KPI Q3 2025", "month": "2025-09"},
    ]

    import random
    random.seed(42)

    grade_map = [
        (91, 100, "A", "Sangat Baik"),
        (80, 90,  "B", "Baik"),
        (75, 79,  "C", "Cukup"),
        (50, 74,  "D", "Perlu Perbaikan"),
    ]

    def _assign_grade(score):
        for low, high, grade, label in grade_map:
            if low <= score <= high:
                return grade, label
        return "E", "Di Bawah Standar"

    for p_idx, pd in enumerate(periods_data):
        period_id = str(uuid.uuid4())
        period_doc = {
            "id": period_id,
            "period_id": period_id,
            "title": pd["title"],
            "name": pd["title"],
            "type": "quarterly",
            "month": pd["month"],
            "status": "finalized",
            "participant_employee_ids": [e["id"] for e in emps],
            "created_at": now,
            "created_by": user.get("id", "system"),
        }
        await db.da_kpi_periods.insert_one(period_doc)
        created_periods.append(period_id)

        # Create results for each employee with varied scores
        for e_idx, emp in enumerate(emps):
            # Give varied scores — some employees consistently high
            base_scores = [92, 85, 78, 88, 72, 95, 83, 76]
            base = base_scores[e_idx % len(base_scores)]
            # Slight variation per period
            variation = random.randint(-3, 5) + p_idx * 2
            score = min(100, max(50, base + variation))
            grade, grade_label = _assign_grade(score)

            result_doc = {
                "id": str(uuid.uuid4()),
                "result_id": str(uuid.uuid4()),      # unique index required
                "period_id": period_id,
                "employee_id": emp["id"],
                "employee_name": emp.get("name", ""),
                "employee_code": emp.get("employee_code", ""),
                "department": emp.get("department", ""),
                "kpi_final": float(score),
                "grade": grade,
                "grade_label": grade_label,
                "raise_pct": 10 if grade == "A" else (7 if grade == "B" else 0),
                "publish_status": "published",
                "published_at": now,
                "created_at": now,
            }
            await db.da_kpi_results.insert_one(result_doc)
            created_results.append(result_doc["id"])

        # Award badges for this period
        await _calculate_and_award_badges(db, period_id)

    total_badges = await db.da_kpi_badges.count_documents({})
    return {
        "ok": True,
        "message": f"Demo seed berhasil: {len(created_periods)} periode, {len(created_results)} hasil, {total_badges} badge",
        "periods_created": len(created_periods),
        "results_created": len(created_results),
        "badges_awarded": total_badges,
        "seeded": True,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# EMPLOYEE PORTAL — MY KPI
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/my/periods")
async def my_periods(request: Request):
    """Daftar periode aktif yang melibatkan karyawan ini."""
    user = await require_auth(request)
    db = get_db()
    emp = await _get_linked_employee(db, user)
    if not emp:
        return {"ok": True, "periods": [], "message": "Akun belum terhubung ke data karyawan."}

    emp_id = emp["id"]
    # Find periods where this employee is a participant
    docs = await db.da_kpi_periods.find(
        {"participant_employee_ids": emp_id, "status": {"$in": ["open", "closed", "finalized"]}},
        {"_id": 0}
    ).sort("created_at", -1).to_list(50)

    result = []
    for d in docs:
        d = _s(d)
        # Check progress for this employee
        my_result = await db.da_kpi_results.find_one(
            {"period_id": d["period_id"], "employee_id": emp_id},
            {"_id": 0, "kpi_final": 1, "grade": 1, "publish_status": 1}
        )
        d["my_result"] = _s(my_result)

        # Count my form completions
        submitted_count = await db.da_kpi_submissions.count_documents(
            {"period_id": d["period_id"], "evaluator_id": emp_id, "status": "submitted"}
        )
        d["my_submitted_forms"] = submitted_count
        result.append(d)

    return {"ok": True, "periods": result}


@router.get("/my/result/{period_id}")
async def my_result(period_id: str, request: Request):
    """Hasil KPI saya untuk periode tertentu (hanya jika sudah dipublish)."""
    user = await require_auth(request)
    db = get_db()
    emp = await _get_linked_employee(db, user)
    if not emp:
        raise HTTPException(409, "Akun belum terhubung ke data karyawan.")

    result = await db.da_kpi_results.find_one(
        {"period_id": period_id, "employee_id": emp["id"]},
        {"_id": 0}
    )
    if not result:
        raise HTTPException(404, "Hasil KPI belum tersedia.")

    if result.get("publish_status") != "published":
        # Return partial info only
        return {
            "ok": True,
            "published": False,
            "message": "Hasil KPI sedang dalam proses finalisasi oleh HR.",
        }

    return {"ok": True, "published": True, "result": _s(result)}


@router.get("/my/results")
async def my_results_history(request: Request):
    """Riwayat semua hasil KPI karyawan yang login."""
    user = await require_auth(request)
    db = get_db()
    emp = await _get_linked_employee(db, user)
    if not emp:
        return {"ok": True, "results": []}

    docs = await db.da_kpi_results.find(
        {"employee_id": emp["id"], "publish_status": "published"},
        {"_id": 0}
    ).sort("created_at", -1).to_list(24)

    # Enrich with period name
    period_ids = [d["period_id"] for d in docs]
    periods = await db.da_kpi_periods.find(
        {"period_id": {"$in": period_ids}}, {"_id": 0, "period_id": 1, "name": 1}
    ).to_list(500) if period_ids else []
    period_map = {p["period_id"]: p["name"] for p in periods}

    result = []
    for d in docs:
        d = _s(d)
        d["period_name"] = period_map.get(d["period_id"], "-")
        result.append(d)

    return {"ok": True, "results": result}


# ═══════════════════════════════════════════════════════════════════════════════
# PROGRESS MONITOR (HR ADMIN)
# ═══════════════════════════════════════════════════════════════════════════════

