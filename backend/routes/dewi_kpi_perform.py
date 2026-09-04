# ruff: noqa: F401
"""
dewi_kpi_perform.py — Performance Scoring & Submissions
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
)
from routes.shared import get_pagination_params, paginated_response
import logging
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/dewi/kpi", tags=["dewi-kpi-perform"])

@router.get("/perform/{period_id}")
async def list_perform_scores(period_id: str, request: Request):
    await _require_hr(request)
    db = get_db()
    sp = request.query_params
    q = {"period_id": period_id}
    # Dual-mode: paginated or full list
    if sp.get("page") or sp.get("limit"):
        page, limit, skip = get_pagination_params(request, default_limit=50)
        total = await db.da_kpi_perform.count_documents(q)
        docs = await db.da_kpi_perform.find(q, {"_id": 0}).skip(skip).limit(limit).to_list(limit)
        emp_ids = [d["employee_id"] for d in docs if d.get("employee_id")]
        emps = await db.rahaza_employees.find({"id": {"$in": emp_ids}}, {"_id": 0, "id": 1, "name": 1, "employee_code": 1}).to_list(500) if emp_ids else []
        emp_map = {e["id"]: e for e in emps}
        result = []
        for d in docs:
            d = _s(d)
            emp = emp_map.get(d.get("employee_id"), {})
            d["employee_name"] = emp.get("name", "-")
            d["employee_code"] = emp.get("employee_code", "-")
            result.append(d)
        return paginated_response(result, total, page, limit)
    docs = await db.da_kpi_perform.find({"period_id": period_id}, {"_id": 0}).to_list(500)

    # Enrich with employee name
    emp_ids = [d["employee_id"] for d in docs if d.get("employee_id")]
    emps = await db.rahaza_employees.find(
        {"id": {"$in": emp_ids}}, {"_id": 0, "id": 1, "name": 1, "employee_code": 1}
    ).to_list(500) if emp_ids else []
    emp_map = {e["id"]: e for e in emps}

    result = []
    for d in docs:
        d = _s(d)
        emp = emp_map.get(d.get("employee_id"), {})
        d["employee_name"] = emp.get("name", "-")
        d["employee_code"] = emp.get("employee_code", "-")
        result.append(d)

    return {"ok": True, "perform_scores": result}


@router.get("/perform/{period_id}/{employee_id}")
async def get_perform_score(period_id: str, employee_id: str, request: Request):
    await require_auth(request)
    db = get_db()
    doc = await db.da_kpi_perform.find_one(
        {"period_id": period_id, "employee_id": employee_id}, {"_id": 0}
    )
    return {"ok": True, "perform": _s(doc)}


@router.put("/perform/{period_id}/{employee_id}")
async def upsert_perform_score(period_id: str, employee_id: str, request: Request):
    user = await _require_hr(request)
    db = get_db()
    body = await request.json()

    # Validate period exists and is open
    period = await db.da_kpi_periods.find_one({"period_id": period_id}, {"_id": 0})
    if not period:
        raise HTTPException(404, "Periode tidak ditemukan.")

    items = body.get("items") or []
    # Calculate perform score from items
    if items:
        total_weight = sum(float(item.get("weight") or 1) for item in items)
        if total_weight > 0:
            weighted_sum = sum(
                float(item.get("score") or 0) * float(item.get("weight") or 1)
                for item in items
            )
            perform_score = round(min(100.0, max(0.0, weighted_sum / total_weight)), 2)
        else:
            perform_score = 0.0
    else:
        # Direct score input
        perform_score = round(min(100.0, max(0.0, float(body.get("perform_score") or 0))), 2)

    doc = {
        "period_id": period_id,
        "employee_id": employee_id,
        "perform_score": perform_score,
        "items": items,
        "notes": body.get("notes") or "",
        "input_by": user["id"],
        "input_by_name": user.get("name", ""),
        "updated_at": _now(),
    }

    existing = await db.da_kpi_perform.find_one({"period_id": period_id, "employee_id": employee_id})
    if existing:
        await db.da_kpi_perform.update_one(
            {"period_id": period_id, "employee_id": employee_id},
            {"$set": doc}
        )
    else:
        doc["item_id"] = _uid()
        doc["created_at"] = _now()
        await db.da_kpi_perform.insert_one(doc)

    out = await db.da_kpi_perform.find_one({"period_id": period_id, "employee_id": employee_id}, {"_id": 0})
    return {"ok": True, "perform": _s(out)}


@router.post("/perform/{period_id}/bulk")
async def bulk_upsert_perform_scores(period_id: str, request: Request):
    """
    Bulk simpan nilai perform untuk banyak karyawan sekaligus.
    Body: { "scores": [{ "employee_id": "...", "perform_score": 85.0, "notes": "..." }, ...] }
    Menghitung atau update langsung perform_score (simple mode, tanpa items breakdown).
    """
    user = await _require_hr(request)
    db = get_db()

    period = await db.da_kpi_periods.find_one({"period_id": period_id}, {"_id": 0})
    if not period:
        raise HTTPException(404, "Periode tidak ditemukan.")

    body = await request.json()
    scores = body.get("scores", [])
    if not scores:
        raise HTTPException(400, "List 'scores' tidak boleh kosong.")

    # Validate employee IDs
    emp_ids = [s["employee_id"] for s in scores if s.get("employee_id")]
    emps = await db.rahaza_employees.find({"id": {"$in": emp_ids}}, {"_id": 0, "id": 1, "name": 1, "employee_code": 1}).to_list(500)
    emp_map = {e["id"]: e for e in emps}

    saved = 0
    skipped = 0
    for s in scores:
        emp_id = s.get("employee_id")
        if not emp_id or emp_id not in emp_map:
            skipped += 1
            continue
        raw_score = s.get("perform_score")
        if raw_score is None:
            skipped += 1
            continue

        perform_score = round(min(100.0, max(0.0, float(raw_score))), 2)
        emp = emp_map[emp_id]

        doc_patch = {
            "period_id": period_id,
            "employee_id": emp_id,
            "employee_name": emp.get("name", "-"),
            "employee_code": emp.get("employee_code", "-"),
            "perform_score": perform_score,
            "notes": s.get("notes", ""),
            "updated_at": _now(),
            "updated_by": user.get("id", ""),
        }

        existing = await db.da_kpi_perform.find_one({"period_id": period_id, "employee_id": emp_id})
        if existing:
            await db.da_kpi_perform.update_one(
                {"period_id": period_id, "employee_id": emp_id},
                {"$set": doc_patch}
            )
        else:
            doc_patch["created_at"] = _now()
            await db.da_kpi_perform.insert_one(doc_patch)
        saved += 1

    return {"ok": True, "saved": saved, "skipped": skipped}


# ═══════════════════════════════════════════════════════════════════════════════
# FORM SUBMISSIONS (EMPLOYEE + SUPERVISOR)
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/my/forms/{period_id}")
async def get_my_forms(period_id: str, request: Request):
    """
    Ambil daftar form yang perlu diisi oleh karyawan yang login.
    Termasuk: self-assessment, peer review assignments, staff→supervisor.
    """
    user = await require_auth(request)
    db = get_db()
    emp = await _get_linked_employee(db, user)

    period = await db.da_kpi_periods.find_one({"period_id": period_id}, {"_id": 0})
    if not period:
        raise HTTPException(404, "Periode tidak ditemukan.")

    if period.get("status") not in ("open", "closed"):
        raise HTTPException(400, "Form belum tersedia (periode belum dibuka).")

    if not emp:
        raise HTTPException(409, "Akun Anda belum terhubung ke data karyawan. Hubungi HR.")

    emp_id = emp["id"]
    peer_assignments = period.get("peer_assignments", [])
    sup_assignments = period.get("supervisor_assignments", [])

    # Find all forms this user needs to fill
    forms_to_fill = []

    # 1. Self-assessment
    self_sub = await db.da_kpi_submissions.find_one(
        {"period_id": period_id, "evaluator_id": emp_id, "eval_type": "self"},
        {"_id": 0}
    )
    forms_to_fill.append({
        "form_type": "self",
        "eval_type": "self",
        "evaluatee_id": emp_id,
        "evaluatee_name": emp.get("name", "Saya"),
        "status": self_sub.get("status", "draft") if self_sub else "not_started",
        "submission_id": self_sub.get("submission_id") if self_sub else None,
        "is_anonymous": False,
    })

    # 2. Peer review (from peer_assignments where reviewer = this employee)
    my_peer_tasks = [a for a in peer_assignments if a["reviewer_id"] == emp_id]
    for pa in my_peer_tasks:
        evaluatee_emp = await db.rahaza_employees.find_one({"id": pa["evaluatee_id"]}, {"_id": 0})
        existing_sub = await db.da_kpi_submissions.find_one(
            {"period_id": period_id, "evaluator_id": emp_id,
             "evaluatee_id": pa["evaluatee_id"], "eval_type": "peer"},
            {"_id": 0}
        )
        forms_to_fill.append({
            "form_type": "peer",
            "eval_type": "peer",
            "evaluatee_id": pa["evaluatee_id"],
            "evaluatee_name": evaluatee_emp.get("name", "?") if evaluatee_emp else "?",
            "status": existing_sub.get("status", "draft") if existing_sub else "not_started",
            "submission_id": existing_sub.get("submission_id") if existing_sub else None,
            "is_anonymous": True,
        })

    # 3. Staff to Supervisor (if employee has a supervisor assigned)
    my_supervisor_id = None
    for sa in sup_assignments:
        if emp_id in sa.get("employee_ids", []):
            my_supervisor_id = sa.get("supervisor_employee_id")
            break

    if my_supervisor_id:
        await db.rahaza_employees.find_one({"id": my_supervisor_id}, {"_id": 0})
        existing_staff_sub = await db.da_kpi_submissions.find_one(
            {"period_id": period_id, "evaluator_id": emp_id,
             "evaluatee_id": my_supervisor_id, "eval_type": "staff_to_supervisor"},
            {"_id": 0}
        )
        forms_to_fill.append({
            "form_type": "staff_to_supervisor",
            "eval_type": "staff_to_supervisor",
            "evaluatee_id": my_supervisor_id,
            "evaluatee_name": "Atasan Saya",  # always anonymous
            "status": existing_staff_sub.get("status", "draft") if existing_staff_sub else "not_started",
            "submission_id": existing_staff_sub.get("submission_id") if existing_staff_sub else None,
            "is_anonymous": True,
        })

    # 4. Supervisor fills forms for subordinates
    is_supervisor = any(sa.get("supervisor_employee_id") == emp_id for sa in sup_assignments)
    supervisor_forms = []
    if is_supervisor:
        for sa in sup_assignments:
            if sa.get("supervisor_employee_id") == emp_id:
                for sub_emp_id in sa.get("employee_ids", []):
                    sub_emp = await db.rahaza_employees.find_one({"id": sub_emp_id}, {"_id": 0})
                    existing_sup_sub = await db.da_kpi_submissions.find_one(
                        {"period_id": period_id, "evaluator_id": emp_id,
                         "evaluatee_id": sub_emp_id, "eval_type": "supervisor_to_staff"},
                        {"_id": 0}
                    )
                    supervisor_forms.append({
                        "form_type": "supervisor_to_staff",
                        "eval_type": "supervisor_to_staff",
                        "evaluatee_id": sub_emp_id,
                        "evaluatee_name": sub_emp.get("name", "?") if sub_emp else "?",
                        "status": existing_sup_sub.get("status", "draft") if existing_sup_sub else "not_started",
                        "submission_id": existing_sup_sub.get("submission_id") if existing_sup_sub else None,
                        "is_anonymous": False,
                    })

    # Get questions by type
    all_q = await db.da_kpi_questions.find({"is_active": True}, {"_id": 0}).sort("order", 1).to_list(500)
    q_by_type = {}
    for q in all_q:
        et = q["eval_type"]
        if et not in q_by_type:
            q_by_type[et] = []
        q_by_type[et].append(q)

    return {
        "ok": True,
        "period": _s(period),
        "employee": _s(emp),
        "forms_to_fill": forms_to_fill,
        "supervisor_forms": supervisor_forms,
        "questions_by_type": q_by_type,
        "total_forms": len(forms_to_fill) + len(supervisor_forms),
        "completed_forms": sum(1 for f in forms_to_fill + supervisor_forms if f["status"] == "submitted"),
    }


