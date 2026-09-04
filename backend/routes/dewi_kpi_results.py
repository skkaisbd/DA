# ruff: noqa: F401
"""
dewi_kpi_results.py — Results Calculation & Management
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
from routes.shared import get_pagination_params, paginated_response
import uuid
import logging
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/dewi/kpi", tags=["dewi-kpi-results"])

@router.post("/submissions")
async def submit_form(request: Request):
    """Submit atau update (save draft) form KPI."""
    user = await require_auth(request)
    db = get_db()
    body = await request.json()

    period_id = body.get("period_id")
    eval_type = body.get("eval_type")
    evaluatee_id = body.get("evaluatee_id")
    answers = body.get("answers") or []
    is_submit = body.get("submit", False)  # False = simpan draft, True = submit final

    if not period_id or not eval_type or not evaluatee_id:
        raise HTTPException(400, "period_id, eval_type, evaluatee_id wajib diisi.")

    emp = await _get_linked_employee(db, user)
    if not emp:
        raise HTTPException(409, "Akun belum terhubung ke data karyawan. Hubungi HR.")
    evaluator_id = emp["id"]

    period = await db.da_kpi_periods.find_one({"period_id": period_id}, {"_id": 0})
    if not period:
        raise HTTPException(404, "Periode tidak ditemukan.")
    if period.get("status") not in ("open",):
        raise HTTPException(400, "Periode tidak dalam status open. Tidak bisa mengisi form.")

    # Validate answers (score 1-5)
    for ans in answers:
        score = ans.get("score")
        if score is not None and (not isinstance(score, (int, float)) or not (1 <= score <= 5)):
            raise HTTPException(400, f"Skor harus antara 1-5. Ditemukan: {score}")

    # Calculate section score
    all_q = await db.da_kpi_questions.find(
        {"eval_type": eval_type, "is_active": True}, {"_id": 0}
    ).to_list(500)
    calc = _calc_section_score(answers, all_q)

    new_status = "submitted" if is_submit else "draft"

    existing = await db.da_kpi_submissions.find_one(
        {"period_id": period_id, "evaluator_id": evaluator_id,
         "evaluatee_id": evaluatee_id, "eval_type": eval_type},
        {"_id": 0}
    )

    if existing and existing.get("status") == "submitted":
        raise HTTPException(400, "Form sudah disubmit dan tidak bisa diubah.")

    doc_upd = {
        "period_id": period_id,
        "eval_type": eval_type,
        "evaluator_id": evaluator_id,
        "evaluatee_id": evaluatee_id,
        "answers": answers,
        "section_score": calc["section_score"],
        "category_breakdown": calc["category_breakdown"],
        "status": new_status,
        "is_anonymous": eval_type in ("peer", "staff_to_supervisor"),
        "updated_at": _now(),
    }
    if is_submit:
        doc_upd["submitted_at"] = _now()

    if existing:
        await db.da_kpi_submissions.update_one(
            {"submission_id": existing["submission_id"]},
            {"$set": doc_upd}
        )
        out = await db.da_kpi_submissions.find_one(
            {"submission_id": existing["submission_id"]}, {"_id": 0}
        )
    else:
        doc_upd["submission_id"] = _uid()
        doc_upd["created_at"] = _now()
        await db.da_kpi_submissions.insert_one(doc_upd)
        out = doc_upd

    return {"ok": True, "submission": _s(out)}


@router.get("/submissions/{period_id}/{employee_id}")
async def get_submission(period_id: str, employee_id: str, request: Request):
    await require_auth(request)
    db = get_db()
    eval_type = request.query_params.get("eval_type")
    filt = {"period_id": period_id, "evaluator_id": employee_id}
    if eval_type:
        filt["eval_type"] = eval_type
    docs = await db.da_kpi_submissions.find(filt, {"_id": 0}).to_list(500)
    return {"ok": True, "submissions": [_s(d) for d in docs]}


# ═══════════════════════════════════════════════════════════════════════════════
# RESULTS — CALCULATE & PUBLISH (HR ADMIN)
# ═══════════════════════════════════════════════════════════════════════════════

@router.post("/results/{period_id}/calculate")
async def calculate_results(period_id: str, request: Request):
    """Hitung KPI untuk semua karyawan dalam periode."""
    user = await _require_hr(request)
    db = get_db()

    period = await db.da_kpi_periods.find_one({"period_id": period_id}, {"_id": 0})
    if not period:
        raise HTTPException(404, "Periode tidak ditemukan.")

    emp_ids = period.get("participant_employee_ids", [])
    if not emp_ids:
        raise HTTPException(400, "Tidak ada karyawan dalam periode ini.")

    emps = await db.rahaza_employees.find(
        {"id": {"$in": emp_ids}}, {"_id": 0}
    ).to_list(500)
    emp_map = {e["id"]: e for e in emps}

    results = []
    for emp_id in emp_ids:
        emp = emp_map.get(emp_id)
        if not emp:
            continue

        # Attitude
        att_data = await _calc_attitude_score(db, period_id, emp_id)
        # Absensi
        abs_data = await _calc_absensi_score(db, period_id, emp_id)
        # Perform
        perf_doc = await db.da_kpi_perform.find_one({"period_id": period_id, "employee_id": emp_id}, {"_id": 0})
        perform_score = perf_doc.get("perform_score") if perf_doc else None

        # Final KPI
        kpi_final = None
        if perform_score is not None and att_data["attitude_score"] is not None and abs_data["absensi_score"] is not None:
            kpi_final = round(
                perform_score * 0.60 +
                att_data["attitude_score"] * 0.20 +
                abs_data["absensi_score"] * 0.20,
                2
            )

        grade_info = _grade(kpi_final) if kpi_final is not None else None

        result_doc = {
            "period_id": period_id,
            "employee_id": emp_id,
            "employee_name": emp.get("name", "-"),
            "employee_code": emp.get("employee_code", "-"),
            "department": emp.get("department") or emp.get("location_id") or "-",
            "perform_score": perform_score,
            "attitude_score": att_data["attitude_score"],
            "attitude_detail": att_data,
            "absensi_score": abs_data["absensi_score"],
            "absensi_detail": abs_data,
            "kpi_final": kpi_final,
            "grade": grade_info.get("grade") if grade_info else None,
            "grade_label": grade_info.get("label") if grade_info else None,
            "status_kpi": grade_info.get("status") if grade_info else None,
            "raise_pct": grade_info.get("raise_pct") if grade_info else None,
            "publish_status": "draft",
            "calculated_at": _now().isoformat(),
            "calculated_by": user["id"],
        }

        # Upsert result
        existing = await db.da_kpi_results.find_one(
            {"period_id": period_id, "employee_id": emp_id}, {"_id": 0}
        )
        if existing:
            await db.da_kpi_results.update_one(
                {"period_id": period_id, "employee_id": emp_id},
                {"$set": result_doc}
            )
        else:
            result_doc["result_id"] = _uid()
            result_doc["created_at"] = _now()
            await db.da_kpi_results.insert_one(result_doc)

        results.append(result_doc)

    return {"ok": True, "calculated": len(results), "results": [_s(r) for r in results]}


@router.get("/results/{period_id}")
async def get_period_results(period_id: str, request: Request):
    await _require_hr(request)
    db = get_db()
    sp = request.query_params
    q = {"period_id": period_id}
    # Dual-mode: paginated or full list
    if sp.get("page") or sp.get("limit"):
        page, limit, skip = get_pagination_params(request, default_limit=50)
        total = await db.da_kpi_results.count_documents(q)
        docs = await db.da_kpi_results.find(q, {"_id": 0}).sort("employee_name", 1).skip(skip).limit(limit).to_list(limit)
        return paginated_response([_s(d) for d in docs], total, page, limit)
    docs = await db.da_kpi_results.find({"period_id": period_id}, {"_id": 0}).sort("employee_name", 1).to_list(500)
    return {"ok": True, "results": [_s(d) for d in docs]}


async def _auto_create_raise_proposals(db, period_id: str, period_name: str, user: dict):
    """
    Auto-create salary raise proposals for Grade A (10%) / B (7%) after KPI publish.
    Idempotent: skip if active proposal already exists for same employee+period.
    Returns {created, skipped}.
    """
    results = await db.da_kpi_results.find(
        {"period_id": period_id, "grade": {"$in": ["A", "B"]}, "kpi_final": {"$ne": None}},
        {"_id": 0}
    ).to_list(500)

    if not results:
        return {"created": 0, "skipped": 0}

    emp_ids = [r["employee_id"] for r in results]
    emps = await db.rahaza_employees.find({"id": {"$in": emp_ids}}, {"_id": 0}).to_list(500)
    emp_map = {e["id"]: e for e in emps}

    profiles = await db.rahaza_payroll_profiles.find(
        {"employee_id": {"$in": emp_ids}, "active": True}, {"_id": 0}
    ).to_list(500)
    profile_map = {p["employee_id"]: p for p in profiles}

    created = 0
    skipped = 0

    for r in results:
        emp_id = r["employee_id"]
        grade = r.get("grade", "")
        raise_pct = r.get("raise_pct") or 0

        if raise_pct <= 0:
            skipped += 1
            continue

        # Idempotency: skip if active kpi_raise proposal already exists for this period
        existing = await db.rahaza_salary_adjustments.find_one({
            "employee_id": emp_id,
            "kpi_period_id": period_id,
            "adjustment_type": "kpi_raise",
            "status": {"$nin": ["rejected", "cancelled"]},
        })
        if existing:
            skipped += 1
            continue

        emp = emp_map.get(emp_id, {})
        profile = profile_map.get(emp_id)
        current_base = float(profile.get("base_rate", 0)) if profile else 0
        if current_base <= 0:
            skipped += 1
            continue

        raise_amount = round(current_base * (raise_pct / 100))
        proposed_base = current_base + raise_amount
        manager_id = emp.get("manager_id") or None

        doc = {
            "id": _uid(),
            "employee_id": emp_id,
            "employee_name": emp.get("name") or r.get("employee_name", "-"),
            "employee_code": emp.get("employee_code") or r.get("employee_code", "-"),
            "manager_id": manager_id,
            "manager_name": emp.get("manager_name", ""),
            "adjustment_type": "kpi_raise",
            "kpi_period_id": period_id,
            "kpi_period_name": period_name,
            "kpi_grade": grade,
            "kpi_final_score": r.get("kpi_final"),
            "current_base": current_base,
            "proposed_base": float(proposed_base),
            "raise_amount": float(raise_amount),
            "raise_pct": raise_pct,
            "reason": f"KPI Grade {grade} ({r.get('grade_label', '')}) — Periode: {period_name}",
            "status": "pending_manager" if manager_id else "pending_hr",
            "created_at": _now(),
            "created_by": user.get("id", ""),
            "notes": "",
            "approval_notes": "",
        }
        await db.rahaza_salary_adjustments.insert_one(doc)
        created += 1

    return {"created": created, "skipped": skipped}


@router.post("/results/{period_id}/publish")
async def publish_results(period_id: str, request: Request):
    """
    Publish hasil KPI — karyawan bisa melihat hasilnya.
    + Validasi completion rate (warn jika <80%).
    + Auto-create raise proposals untuk Grade A/B.

    Body: { "force": true } untuk bypass peringatan <80%.
    """
    user = await _require_hr(request)
    db = get_db()

    body = {}
    try:
        body = await request.json()
    except Exception:
        logging.getLogger(__name__).debug("suppressed exception", exc_info=True)
    force = bool(body.get("force", False))

    period = await db.da_kpi_periods.find_one({"period_id": period_id}, {"_id": 0})
    if not period:
        raise HTTPException(404, "Periode tidak ditemukan.")

    # ── Completion rate check ──────────────────────────────────────────────
    total_participants = len(period.get("participant_employee_ids", []))
    finalized_count = await db.da_kpi_results.count_documents(
        {"period_id": period_id, "kpi_final": {"$ne": None}}
    )
    completion_pct = round((finalized_count / total_participants * 100), 1) if total_participants > 0 else 0

    if completion_pct < 80 and not force:
        return {
            "ok": False,
            "warning": True,
            "message": (
                f"Baru {completion_pct}% karyawan memiliki KPI final terhitung "
                f"({finalized_count}/{total_participants}). "
                f"Kirim dengan force=true untuk tetap lanjutkan."
            ),
            "completion_pct": completion_pct,
            "finalized_count": finalized_count,
            "total_participants": total_participants,
        }

    # ── Publish ────────────────────────────────────────────────────────────
    await db.da_kpi_results.update_many(
        {"period_id": period_id, "kpi_final": {"$ne": None}},
        {"$set": {"publish_status": "published", "published_at": _now(), "published_by": user["id"]}}
    )
    await db.da_kpi_periods.update_one(
        {"period_id": period_id},
        {"$set": {"status": "finalized", "finalized_at": _now(), "finalized_by": user["id"]}}
    )
    count = await db.da_kpi_results.count_documents({"period_id": period_id, "publish_status": "published"})

    # ── Auto Raise Proposals (Grade A/B) ───────────────────────────────────
    raise_result = await _auto_create_raise_proposals(db, period_id, period.get("name", ""), user)

    return {
        "ok": True,
        "published": count,
        "completion_pct": completion_pct,
        "raise_proposals": raise_result,
        "badges_awarded": await _calculate_and_award_badges(db, period_id),
    }




