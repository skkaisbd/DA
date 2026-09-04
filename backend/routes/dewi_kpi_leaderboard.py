# ruff: noqa: F401
"""
dewi_kpi_leaderboard.py — Leaderboard & Achievements
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
    BADGE_DEFS,
)
import logging
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/dewi/kpi", tags=["dewi-kpi-leaderboard"])

@router.get("/leaderboard/{period_id}")
async def get_leaderboard(period_id: str, request: Request, limit: int = Query(default=20)):
    """Leaderboard KPI untuk satu periode — sorted by kpi_final DESC."""
    await require_auth(request)
    db = get_db()

    results = await db.da_kpi_results.find(
        {"period_id": period_id, "kpi_final": {"$ne": None}},
        {"_id": 0}
    ).to_list(500)

    if not results:
        return {"ok": True, "leaderboard": [], "period_id": period_id}

    sorted_res = sorted(results, key=lambda r: float(r.get("kpi_final") or 0), reverse=True)

    # Get prev period scores for delta
    prev_results = await db.da_kpi_results.find(
        {"period_id": {"$ne": period_id}, "kpi_final": {"$ne": None}},
        {"_id": 0, "employee_id": 1, "kpi_final": 1}
    ).to_list(500)
    prev_map = {}
    for pr in prev_results:
        eid = pr["employee_id"]
        if eid not in prev_map:
            prev_map[eid] = float(pr.get("kpi_final") or 0)

    # Get badges for this period
    badges_docs = await db.da_kpi_badges.find({"period_id": period_id}, {"_id": 0}).to_list(500)
    badges_map: dict = {}
    for b in badges_docs:
        eid = b["employee_id"]
        if eid not in badges_map:
            badges_map[eid] = []
        badges_map[eid].append({
            "badge_type": b["badge_type"],
            "badge_emoji": b.get("badge_emoji", ""),
            "badge_label": b.get("badge_label", ""),
        })

    leaderboard = []
    for rank_idx, r in enumerate(sorted_res[:limit]):
        emp_id = r["employee_id"]
        score = float(r.get("kpi_final") or 0)
        prev_score = prev_map.get(emp_id)
        delta = round(score - prev_score, 1) if prev_score is not None else None

        leaderboard.append({
            "rank": rank_idx + 1,
            "employee_id": emp_id,
            "employee_name": r.get("employee_name", ""),
            "employee_code": r.get("employee_code", ""),
            "department": r.get("department", ""),
            "score": round(score, 1),
            "grade": r.get("grade"),
            "grade_label": r.get("grade_label", ""),
            "prev_score": round(prev_score, 1) if prev_score is not None else None,
            "delta": delta,
            "badges": badges_map.get(emp_id, []),
        })

    return {
        "ok": True,
        "period_id": period_id,
        "total": len(sorted_res),
        "leaderboard": leaderboard,
    }


@router.get("/leaderboard")
async def get_overall_leaderboard(request: Request, limit: int = Query(default=20)):
    """All-time leaderboard — rata-rata score semua periode per karyawan."""
    await require_auth(request)
    db = get_db()

    results = await db.da_kpi_results.find(
        {"kpi_final": {"$ne": None}}, {"_id": 0}
    ).to_list(500)

    if not results:
        return {"ok": True, "leaderboard": []}

    from collections import defaultdict
    emp_scores: dict = defaultdict(list)
    emp_info: dict = {}
    for r in results:
        eid = r["employee_id"]
        emp_scores[eid].append(float(r.get("kpi_final") or 0))
        emp_info[eid] = {
            "employee_name": r.get("employee_name", ""),
            "employee_code": r.get("employee_code", ""),
            "department": r.get("department", ""),
        }

    leaderboard = []
    for eid, scores in emp_scores.items():
        avg = round(sum(scores) / len(scores), 1)
        leaderboard.append({
            "employee_id": eid,
            "employee_name": emp_info[eid]["employee_name"],
            "employee_code": emp_info[eid]["employee_code"],
            "department": emp_info[eid]["department"],
            "avg_score": avg,
            "period_count": len(scores),
            "best_score": round(max(scores), 1),
            "total_badges": await db.da_kpi_badges.count_documents({"employee_id": eid}),
        })

    leaderboard.sort(key=lambda x: x["avg_score"], reverse=True)
    for i, entry in enumerate(leaderboard):
        entry["rank"] = i + 1

    return {"ok": True, "leaderboard": leaderboard[:limit]}


@router.get("/achievements/{employee_id}")
async def get_employee_achievements(employee_id: str, request: Request):
    """Semua badge milik satu karyawan, dikelompokkan per tipe."""
    await require_auth(request)
    db = get_db()

    badges = await db.da_kpi_badges.find(
        {"employee_id": employee_id}, {"_id": 0}
    ).sort("earned_at", -1).to_list(500)

    # Enrich with badge def info
    enriched = []
    for b in badges:
        btype = b.get("badge_type", "")
        bdef = BADGE_DEFS.get(btype, {})
        enriched.append({
            **_s(b),
            "badge_color": bdef.get("color", "#888"),
            "badge_desc": bdef.get("desc", ""),
        })

    # Summary by badge type
    from collections import Counter
    type_counts = Counter(b["badge_type"] for b in badges)
    summary = [
        {
            "badge_type": btype,
            "count": cnt,
            "badge_emoji": BADGE_DEFS.get(btype, {}).get("emoji", ""),
            "badge_label": BADGE_DEFS.get(btype, {}).get("label", btype),
            "badge_color": BADGE_DEFS.get(btype, {}).get("color", "#888"),
        }
        for btype, cnt in type_counts.most_common()
    ]

    return {"ok": True, "employee_id": employee_id, "badges": enriched, "summary": summary, "total": len(badges)}


@router.get("/my/achievements")
async def my_achievements(request: Request):
    """Badge milik karyawan yang sedang login."""
    user = await require_auth(request)
    db = get_db()
    emp = await _get_linked_employee(db, user)
    if not emp:
        return {"ok": True, "badges": [], "summary": [], "total": 0}
    return await get_employee_achievements(emp["id"], request)


