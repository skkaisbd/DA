# ruff: noqa: F401
"""
dewi_kpi_reports.py — Reports, Trends & Analytics
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
import logging
from datetime import datetime, timezone
from typing import Optional
from utils.waktu import now_wib

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/dewi/kpi", tags=["dewi-kpi-reports"])

@router.get("/monitor/{period_id}")
async def monitor_progress(period_id: str, request: Request):
    await _require_hr(request)
    db = get_db()

    period = await db.da_kpi_periods.find_one({"period_id": period_id}, {"_id": 0})
    if not period:
        raise HTTPException(404, "Periode tidak ditemukan.")

    emp_ids = period.get("participant_employee_ids", [])
    emps = await db.rahaza_employees.find(
        {"id": {"$in": emp_ids}}, {"_id": 0, "id": 1, "name": 1, "employee_code": 1, "department": 1}
    ).to_list(500) if emp_ids else []

    result = []
    for emp in emps:
        emp_id = emp["id"]

        # Check submissions
        self_done = await db.da_kpi_submissions.count_documents(
            {"period_id": period_id, "evaluator_id": emp_id, "eval_type": "self", "status": "submitted"}
        ) > 0
        peer_total = sum(1 for a in period.get("peer_assignments", []) if a["reviewer_id"] == emp_id)
        peer_done = await db.da_kpi_submissions.count_documents(
            {"period_id": period_id, "evaluator_id": emp_id, "eval_type": "peer", "status": "submitted"}
        )
        staff_sup_done = await db.da_kpi_submissions.count_documents(
            {"period_id": period_id, "evaluator_id": emp_id, "eval_type": "staff_to_supervisor", "status": "submitted"}
        ) > 0

        # Check supervisor forms for this employee
        sup_reviewed = await db.da_kpi_submissions.count_documents(
            {"period_id": period_id, "evaluatee_id": emp_id, "eval_type": "supervisor_to_staff", "status": "submitted"}
        ) > 0

        # Check perform score
        perf_doc = await db.da_kpi_perform.find_one({"period_id": period_id, "employee_id": emp_id}, {"_id": 0})

        result.append({
            "employee_id": emp_id,
            "employee_name": emp.get("name", "-"),
            "employee_code": emp.get("employee_code", "-"),
            "department": emp.get("department") or "-",
            "self_done": self_done,
            "peer_done": peer_done,
            "peer_total": peer_total,
            "staff_to_sup_done": staff_sup_done,
            "supervisor_reviewed": sup_reviewed,
            "perform_input": perf_doc is not None,
            "perform_score": perf_doc.get("perform_score") if perf_doc else None,
        })

    return {"ok": True, "period": _s(period), "progress": result}


# ═══════════════════════════════════════════════════════════════════════════════
# REPORT / SUMMARY (HR & SUPERVISOR)
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/reports/summary/{period_id}")
async def report_summary(period_id: str, request: Request):
    """Laporan ringkasan KPI per periode (untuk HR & Supervisor)."""
    await _require_hr(request)
    db = get_db()

    results = await db.da_kpi_results.find(
        {"period_id": period_id}, {"_id": 0}
    ).sort("employee_name", 1).to_list(500)

    if not results:
        return {"ok": True, "period_id": period_id, "summary": {}, "details": []}

    # Summary statistics
    finalized = [r for r in results if r.get("kpi_final") is not None]
    if finalized:
        avg_kpi = round(sum(r["kpi_final"] for r in finalized) / len(finalized), 2)
        avg_perform = round(sum(r["perform_score"] or 0 for r in finalized) / len(finalized), 2)
        avg_attitude = round(sum(r["attitude_score"] or 0 for r in finalized) / len(finalized), 2)
        avg_absensi = round(sum(r["absensi_score"] or 0 for r in finalized) / len(finalized), 2)
        grade_dist = {"A": 0, "B": 0, "C": 0, "D": 0, "E": 0}
        for r in finalized:
            g = r.get("grade")
            if g in grade_dist:
                grade_dist[g] += 1
    else:
        avg_kpi = avg_perform = avg_attitude = avg_absensi = 0
        grade_dist = {"A": 0, "B": 0, "C": 0, "D": 0, "E": 0}

    return {
        "ok": True,
        "period_id": period_id,
        "total_employees": len(results),
        "finalized_count": len(finalized),
        "summary": {
            "avg_kpi": avg_kpi,
            "avg_perform": avg_perform,
            "avg_attitude": avg_attitude,
            "avg_absensi": avg_absensi,
            "grade_distribution": grade_dist,
        },
        "details": [_s(r) for r in results],
    }



# ═══════════════════════════════════════════════════════════════════════════════
# TREND — Historical KPI per Karyawan (last N finalized periods)
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/trend/{employee_id}")
async def employee_kpi_trend(employee_id: str, request: Request, limit: int = 6):
    """
    Tren KPI historis untuk satu karyawan (default: 6 periode terakhir yang sudah finalized).
    Returns daftar periode + skor untuk chart visualisasi.
    """
    await require_auth(request)
    db = get_db()

    # Get finalized periods
    all_periods = await db.da_kpi_periods.find(
        {"status": "finalized", "participant_employee_ids": employee_id},
        {"_id": 0, "period_id": 1, "name": 1, "month": 1, "year": 1, "finalized_at": 1}
    ).sort("year", -1).sort("month", -1).to_list(500)

    # Pick last `limit` periods
    target_periods = all_periods[:limit]
    target_periods.reverse()  # chronological order

    period_ids = [p["period_id"] for p in target_periods]
    {p["period_id"]: p for p in target_periods}

    results = await db.da_kpi_results.find(
        {"period_id": {"$in": period_ids}, "employee_id": employee_id},
        {"_id": 0}
    ).to_list(500)
    result_map = {r["period_id"]: r for r in results}

    # Also get dept avg per period
    dept_avgs = {}
    emp = await db.rahaza_employees.find_one({"id": employee_id}, {"_id": 0, "department": 1})
    emp_dept = (emp or {}).get("department")

    if emp_dept:
        for pid in period_ids:
            dept_emps = await db.rahaza_employees.distinct("id", {"department": emp_dept})
            dept_results = await db.da_kpi_results.find(
                {"period_id": pid, "employee_id": {"$in": dept_emps}, "kpi_final": {"$ne": None}},
                {"_id": 0, "kpi_final": 1}
            ).to_list(500)
            if dept_results:
                dept_avgs[pid] = round(sum(r["kpi_final"] for r in dept_results) / len(dept_results), 2)

    trend = []
    for p in target_periods:
        pid = p["period_id"]
        r = result_map.get(pid, {})
        trend.append({
            "period_id": pid,
            "period_name": p.get("name", f"M{p.get('month')}/{p.get('year')}"),
            "month": p.get("month"),
            "year": p.get("year"),
            "kpi_final": r.get("kpi_final"),
            "perform_score": r.get("perform_score"),
            "attitude_score": r.get("attitude_score"),
            "absensi_score": r.get("absensi_score"),
            "grade": r.get("grade"),
            "dept_avg": dept_avgs.get(pid),
        })

    return {
        "ok": True,
        "employee_id": employee_id,
        "department": emp_dept,
        "trend": trend,
    }


@router.get("/trend")
async def all_employees_trend(request: Request, period_count: int = 6):
    """Rata-rata KPI tren untuk semua karyawan (departemen & perusahaan)."""
    await _require_hr(request)
    db = get_db()

    periods = await db.da_kpi_periods.find(
        {"status": "finalized"},
        {"_id": 0, "period_id": 1, "name": 1, "month": 1, "year": 1}
    ).sort([("year", -1), ("month", -1)]).to_list(period_count)
    periods.reverse()

    trend = []
    for p in periods:
        pid = p["period_id"]
        results = await db.da_kpi_results.find(
            {"period_id": pid, "kpi_final": {"$ne": None}},
            {"_id": 0, "kpi_final": 1, "grade": 1}
        ).to_list(500)
        if results:
            avg = round(sum(r["kpi_final"] for r in results) / len(results), 2)
            grade_dist = {"A": 0, "B": 0, "C": 0, "D": 0, "E": 0}
            for r in results:
                if r.get("grade") in grade_dist:
                    grade_dist[r["grade"]] += 1
        else:
            avg = None
            grade_dist = {"A": 0, "B": 0, "C": 0, "D": 0, "E": 0}

        trend.append({
            "period_id": pid,
            "period_name": p.get("name", f"M{p.get('month')}/{p.get('year')}"),
            "month": p.get("month"),
            "year": p.get("year"),
            "company_avg": avg,
            "total_employees": len(results),
            "grade_distribution": grade_dist,
        })

    return {"ok": True, "trend": trend}


# ═══════════════════════════════════════════════════════════════════════════════
# GOALS — Goal Setting & Progress Tracking per Karyawan per Periode
# ═══════════════════════════════════════════════════════════════════════════════

def _goal_status(progress_pct: float) -> str:
    if progress_pct >= 100:
        return "achieved"
    elif progress_pct >= 70:
        return "on_track"
    elif progress_pct >= 40:
        return "at_risk"
    else:
        return "missed"


@router.get("/goals")
async def list_goals(request: Request, period_id: str = None, employee_id: str = None):
    """List goals per periode / per karyawan."""
    user = await require_auth(request)
    db = get_db()

    q = {}
    if period_id:
        q["period_id"] = period_id
    if employee_id:
        q["employee_id"] = employee_id
    # Non-HR only sees their own goals
    role = (user.get("role") or "").lower()
    if role not in ("superadmin", "admin", "owner", "hr", "manager"):
        emp = await db.rahaza_employees.find_one({"user_id": user["id"]}, {"_id": 0, "id": 1})
        if emp:
            q["employee_id"] = emp["id"]

    docs = await db.da_kpi_goals.find(q, {"_id": 0}).sort("created_at", 1).to_list(500)
    return {"ok": True, "goals": [_s(d) for d in docs]}


@router.post("/goals")
async def create_goal(request: Request):
    """Buat goal baru untuk karyawan di suatu periode."""
    user = await _require_hr(request)
    db = get_db()

    body = await request.json()
    period_id = body.get("period_id")
    employee_id = body.get("employee_id")
    if not period_id or not employee_id:
        raise HTTPException(400, "period_id dan employee_id wajib diisi.")

    period = await db.da_kpi_periods.find_one({"period_id": period_id}, {"_id": 0, "name": 1})
    emp = await db.rahaza_employees.find_one({"id": employee_id}, {"_id": 0, "name": 1, "employee_code": 1})

    target_value = float(body.get("target_value") or 0)
    actual_value = float(body.get("actual_value") or 0)
    progress_pct = round((actual_value / target_value * 100), 1) if target_value > 0 else 0

    doc = {
        "goal_id": _uid(),
        "period_id": period_id,
        "period_name": (period or {}).get("name", period_id),
        "employee_id": employee_id,
        "employee_name": (emp or {}).get("name", "-"),
        "employee_code": (emp or {}).get("employee_code", "-"),
        "title": body.get("title", ""),
        "description": body.get("description", ""),
        "target_value": target_value,
        "unit": body.get("unit", ""),
        "actual_value": actual_value,
        "progress_pct": progress_pct,
        "status": _goal_status(progress_pct),
        "notes": body.get("notes", ""),
        "created_at": _now(),
        "updated_at": _now(),
        "created_by": user.get("id", ""),
    }
    await db.da_kpi_goals.insert_one(doc)
    return {"ok": True, "goal": _s(doc)}


@router.put("/goals/{goal_id}")
async def update_goal(goal_id: str, request: Request):
    """Update goal (termasuk progress actual_value)."""
    user = await require_auth(request)
    db = get_db()

    body = await request.json()
    goal = await db.da_kpi_goals.find_one({"goal_id": goal_id}, {"_id": 0})
    if not goal:
        raise HTTPException(404, "Goal tidak ditemukan.")

    updates = {}
    for field in ("title", "description", "unit", "notes"):
        if field in body:
            updates[field] = body[field]
    if "target_value" in body:
        updates["target_value"] = float(body["target_value"] or 0)
    if "actual_value" in body:
        updates["actual_value"] = float(body["actual_value"] or 0)

    tv = updates.get("target_value", goal.get("target_value", 0))
    av = updates.get("actual_value", goal.get("actual_value", 0))
    if tv and tv > 0:
        updates["progress_pct"] = round((av / tv) * 100, 1)
        updates["status"] = _goal_status(updates["progress_pct"])

    updates["updated_at"] = _now()
    updates["updated_by"] = user.get("id", "")

    await db.da_kpi_goals.update_one({"goal_id": goal_id}, {"$set": updates})
    updated = await db.da_kpi_goals.find_one({"goal_id": goal_id}, {"_id": 0})
    return {"ok": True, "goal": _s(updated)}


@router.delete("/goals/{goal_id}")
async def delete_goal(goal_id: str, request: Request):
    """Hapus goal."""
    await _require_hr(request)
    db = get_db()

    res = await db.da_kpi_goals.delete_one({"goal_id": goal_id})
    if res.deleted_count == 0:
        raise HTTPException(404, "Goal tidak ditemukan.")
    return {"ok": True, "message": "Goal dihapus"}


# ═══════════════════════════════════════════════════════════════════════════════
# KPI STATS — Dashboard overview
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/stats")
async def kpi_stats(request: Request):
    """Stats ringkasan KPI: aktif periode, distribusi grade, avg KPI terkini."""
    await _require_hr(request)
    db = get_db()

    open_count = await db.da_kpi_periods.count_documents({"status": "open"})
    draft_count = await db.da_kpi_periods.count_documents({"status": "draft"})
    finalized_count = await db.da_kpi_periods.count_documents({"status": "finalized"})

    # Rata-rata KPI dari periode finalized terakhir
    last_period = await db.da_kpi_periods.find_one(
        {"status": "finalized"}, {"_id": 0, "period_id": 1, "name": 1},
        sort=[("year", -1), ("month", -1)]
    )
    last_avg = None
    last_grade_dist = {"A": 0, "B": 0, "C": 0, "D": 0, "E": 0}
    if last_period:
        results = await db.da_kpi_results.find(
            {"period_id": last_period["period_id"], "kpi_final": {"$ne": None}},
            {"_id": 0, "kpi_final": 1, "grade": 1}
        ).to_list(500)
        if results:
            last_avg = round(sum(r["kpi_final"] for r in results) / len(results), 2)
            for r in results:
                if r.get("grade") in last_grade_dist:
                    last_grade_dist[r["grade"]] += 1

    # Pending raise proposals from KPI
    pending_raises = await db.rahaza_salary_adjustments.count_documents(
        {"adjustment_type": "kpi_raise", "status": {"$in": ["pending_manager", "pending_hr"]}}
    )

    return {
        "ok": True,
        "periods": {
            "open": open_count,
            "draft": draft_count,
            "finalized": finalized_count,
        },
        "last_period": _s(last_period) if last_period else None,
        "last_period_avg": last_avg,
        "last_period_grade_dist": last_grade_dist,
        "pending_raise_proposals": pending_raises,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# PDF EXPORT — Laporan KPI per Karyawan
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/results/{period_id}/{employee_id}/pdf")
async def export_employee_kpi_pdf(period_id: str, employee_id: str, request: Request, token: str = None):
    """Generate PDF laporan KPI untuk satu karyawan dalam satu periode."""
    from fastapi.responses import Response
    import io
    from auth import JWT_SECRET
    import jwt as _jwt

    # Support token via query param (for browser window.open)
    if token:
        try:
            _jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
        except Exception:
            from fastapi import HTTPException as _HTTPException
            raise _HTTPException(401, "Token tidak valid")
    else:
        await require_auth(request)
    db = get_db()

    period = await db.da_kpi_periods.find_one({"period_id": period_id}, {"_id": 0})
    if not period:
        raise HTTPException(404, "Periode tidak ditemukan.")

    result = await db.da_kpi_results.find_one(
        {"period_id": period_id, "employee_id": employee_id}, {"_id": 0}
    )
    emp = await db.rahaza_employees.find_one({"id": employee_id}, {"_id": 0})
    perform = await db.da_kpi_perform.find_one(
        {"period_id": period_id, "employee_id": employee_id}, {"_id": 0}
    )
    goals = await db.da_kpi_goals.find(
        {"period_id": period_id, "employee_id": employee_id}, {"_id": 0}
    ).to_list(500)

    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import cm
        from reportlab.lib import colors
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
        from reportlab.lib.enums import TA_CENTER, TA_LEFT

        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=2*cm, bottomMargin=2*cm,
                                leftMargin=2*cm, rightMargin=2*cm)
        styles = getSampleStyleSheet()
        story = []

        # Title
        title_style = ParagraphStyle('title', parent=styles['Heading1'],
                                     fontSize=16, textColor=colors.HexColor('#1e293b'),
                                     alignment=TA_CENTER, spaceAfter=6)
        subtitle_style = ParagraphStyle('subtitle', parent=styles['Normal'],
                                        fontSize=10, textColor=colors.HexColor('#64748b'),
                                        alignment=TA_CENTER, spaceAfter=12)
        ParagraphStyle('label', parent=styles['Normal'],
                                     fontSize=9, textColor=colors.HexColor('#475569'))
        ParagraphStyle('value', parent=styles['Normal'],
                                     fontSize=10, textColor=colors.HexColor('#0f172a'))

        story.append(Paragraph("LAPORAN KPI KARYAWAN", title_style))
        story.append(Paragraph(f"CV. Dewi Aditya — {period.get('name', period_id)}", subtitle_style))

        grade_info = _grade(result.get("kpi_final", 0)) if result else {}
        grade_str = grade_info.get("grade", "—") if grade_info else "—"
        kpi_final = result.get("kpi_final") if result else None
        raise_pct = grade_info.get("raise_pct", 0) if grade_info else 0

        # Employee Info
        emp_data = [
            ["Nama Karyawan", emp.get("name", "-") if emp else "-",
             "NIK / Kode", emp.get("employee_code", "-") if emp else "-"],
            ["Departemen", emp.get("department", "-") if emp else "-",
             "Jabatan", emp.get("position", "-") if emp else "-"],
            ["Periode", period.get("name", period_id), "Tahun", str(period.get("year", ""))],
        ]
        emp_table = Table(emp_data, colWidths=[3.5*cm, 5.5*cm, 3.5*cm, 4.5*cm])
        emp_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f8fafc')),
            ('TEXTCOLOR', (0, 0), (0, -1), colors.HexColor('#64748b')),
            ('TEXTCOLOR', (2, 0), (2, -1), colors.HexColor('#64748b')),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e2e8f0')),
            ('ROWBACKGROUNDS', (0, 0), (-1, -1), [colors.HexColor('#f8fafc'), colors.HexColor('#f1f5f9')]),
            ('PADDING', (0, 0), (-1, -1), 6),
        ]))
        story.append(emp_table)
        story.append(Spacer(1, 0.5*cm))

        # Score Summary
        story.append(Paragraph("<b>Ringkasan Nilai KPI</b>", styles['Heading3']))
        score_data = [
            ["Komponen", "Bobot", "Nilai", "Kontribusi"],
            ["Perform Score", "60%",
             f"{result.get('perform_score', 0):.1f}" if result else "—",
             f"{(result.get('perform_score', 0) * 0.6):.1f}" if result else "—"],
            ["Attitude Score (360°)", "20%",
             f"{result.get('attitude_score', 0):.1f}" if result else "—",
             f"{(result.get('attitude_score', 0) * 0.2):.1f}" if result else "—"],
            ["Absensi Score", "20%",
             f"{result.get('absensi_score', 0):.1f}" if result else "—",
             f"{(result.get('absensi_score', 0) * 0.2):.1f}" if result else "—"],
            ["KPI FINAL", "100%",
             f"{kpi_final:.1f}" if kpi_final else "—",
             f"Grade: {grade_str} | Raise: {raise_pct}%" if kpi_final else "—"],
        ]
        grade_color = {'A': '#10b981', 'B': '#3b82f6', 'C': '#f59e0b', 'D': '#f97316', 'E': '#ef4444'}.get(grade_str, '#64748b')
        score_table = Table(score_data, colWidths=[7*cm, 2.5*cm, 2.5*cm, 5*cm])
        score_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1e293b')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e2e8f0')),
            ('ROWBACKGROUNDS', (0, 1), (-1, -2), [colors.white, colors.HexColor('#f8fafc')]),
            ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor(grade_color)),
            ('TEXTCOLOR', (0, -1), (-1, -1), colors.white),
            ('FONTSIZE', (0, -1), (-1, -1), 10),
            ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
            ('PADDING', (0, 0), (-1, -1), 6),
        ]))
        story.append(score_table)
        story.append(Spacer(1, 0.4*cm))

        # Goals
        if goals:
            story.append(Paragraph("<b>Goals & Pencapaian</b>", styles['Heading3']))
            goal_data = [["Goal", "Target", "Aktual", "Progress", "Status"]]
            for g in goals:
                status_label = {"achieved": "Tercapai", "on_track": "On Track",
                                "at_risk": "At Risk", "missed": "Missed"}.get(g.get("status", ""), "-")
                goal_data.append([
                    g.get("title", "-"),
                    f"{g.get('target_value', 0)} {g.get('unit', '')}".strip(),
                    f"{g.get('actual_value', 0)} {g.get('unit', '')}".strip(),
                    f"{g.get('progress_pct', 0):.1f}%",
                    status_label,
                ])
            goal_table = Table(goal_data, colWidths=[5.5*cm, 2.5*cm, 2.5*cm, 2*cm, 2.5*cm])
            goal_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#334155')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('FONTSIZE', (0, 0), (-1, -1), 8),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e2e8f0')),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8fafc')]),
                ('PADDING', (0, 0), (-1, -1), 5),
            ]))
            story.append(goal_table)
            story.append(Spacer(1, 0.4*cm))

        # Perform items
        if perform and perform.get("items"):
            story.append(Paragraph("<b>Rincian Nilai Perform</b>", styles['Heading3']))
            perf_data = [["KPI Item", "Target", "Aktual", "Nilai", "Bobot"]]
            for it in perform["items"]:
                perf_data.append([
                    it.get("label", "-"),
                    str(it.get("target", "-")),
                    str(it.get("actual", "-")),
                    f"{it.get('score', 0):.1f}",
                    f"{it.get('weight', 1):.1f}",
                ])
            perf_table = Table(perf_data, colWidths=[6*cm, 2.5*cm, 2.5*cm, 2*cm, 2*cm])
            perf_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#334155')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('FONTSIZE', (0, 0), (-1, -1), 8),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e2e8f0')),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8fafc')]),
                ('PADDING', (0, 0), (-1, -1), 5),
            ]))
            story.append(perf_table)
            story.append(Spacer(1, 0.4*cm))

        # Footer
        from datetime import datetime
        footer_text = (
            f"Dokumen ini dihasilkan otomatis oleh CV. Dewi Aditya pada "
            f"{now_wib().strftime('%d %B %Y %H:%M')} WIB. "
            f"RAHASIA — Hanya untuk penggunaan internal."
        )
        story.append(Spacer(1, 0.5*cm))
        story.append(Paragraph(footer_text, ParagraphStyle(
            'footer', parent=styles['Normal'],
            fontSize=7, textColor=colors.HexColor('#94a3b8'),
            alignment=TA_CENTER
        )))

        doc.build(story)
        buffer.seek(0)

        safe_name = (emp.get("name", "karyawan") if emp else "karyawan").replace(" ", "_")
        filename = f"KPI_{safe_name}_{period.get('name', period_id).replace(' ', '_')}.pdf"

        return Response(
            content=buffer.getvalue(),
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    except ImportError:
        raise HTTPException(500, "Library reportlab tidak tersedia.")
    except Exception as e:
        raise HTTPException(500, f"Gagal generate PDF: {str(e)}")


# ═══════════════════════════════════════════════════════════════════════════════
# PEER REVIEW FAIRNESS CHECK
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/fairness/{period_id}")
async def peer_review_fairness_check(period_id: str, request: Request):
    """
    P2.3: Peer Review Fairness Check untuk satu periode KPI.

    Checks:
    1. Karyawan dengan peer reviewer < 3 (terlalu sedikit reviewers)
    2. Direct-report conflict: reviewer adalah bawahan langsung evaluatee
    3. Rating variance antar peer reviewers > 2 poin (potential bias)

    Returns severity: ok | warning | error per employee.
    """
    await _require_hr(request)
    db = get_db()

    period = await db.da_kpi_periods.find_one({"period_id": period_id}, {"_id": 0})
    if not period:
        raise HTTPException(404, "Periode tidak ditemukan.")

    peer_assignments = period.get("peer_assignments", [])
    participant_ids = period.get("participant_employee_ids", [])

    # Enrich with employee data
    all_ids = list(set(participant_ids + [a["reviewer_id"] for a in peer_assignments] + [a["evaluatee_id"] for a in peer_assignments]))
    emps = await db.rahaza_employees.find(
        {"id": {"$in": all_ids}},
        {"_id": 0, "id": 1, "name": 1, "employee_code": 1, "manager_id": 1}
    ).to_list(500)
    emp_map = {e["id"]: e for e in emps}

    # Build reviewer map: evaluatee_id → list of reviewer_ids
    reviewer_map: dict[str, list] = {pid: [] for pid in participant_ids}
    for a in peer_assignments:
        ev_id = a.get("evaluatee_id")
        rv_id = a.get("reviewer_id")
        if ev_id in reviewer_map and rv_id:
            reviewer_map[ev_id].append(rv_id)

    # Get submitted peer scores for variance calculation
    submitted = await db.da_kpi_submissions.find(
        {"period_id": period_id, "eval_type": "peer"},
        {"_id": 0, "evaluatee_id": 1, "evaluator_id": 1, "avg_score": 1}
    ).to_list(500)
    scores_map: dict[str, list] = {}
    for s in submitted:
        ev_id = s.get("evaluatee_id")
        if ev_id:
            scores_map.setdefault(ev_id, []).append(s.get("avg_score", 0) or 0)

    issues = []
    warnings_count = 0
    errors_count = 0
    ok_count = 0

    for emp_id in participant_ids:
        emp = emp_map.get(emp_id, {})
        emp_name = emp.get("name", emp_id[:8])
        emp_code = emp.get("employee_code", "")
        reviewers = reviewer_map.get(emp_id, [])
        reviewer_count = len(reviewers)
        emp_issues = []
        severity = "ok"

        # Check 1: Not enough peer reviewers
        if reviewer_count < 3:
            msg = f"Hanya {reviewer_count} peer reviewer (minimum 3)"
            emp_issues.append({"code": "low_reviewer_count", "severity": "warning", "message": msg})
            severity = "warning"

        # Check 2: Direct-report conflict (reviewer is a bawahan from employee)
        conflicts = []
        for rv_id in reviewers:
            rv_emp = emp_map.get(rv_id, {})
            if rv_emp.get("manager_id") == emp_id:
                conflicts.append(rv_emp.get("name", rv_id[:8]))
        if conflicts:
            msg = f"Konflik langsung: {', '.join(conflicts)} adalah bawahan langsung"
            emp_issues.append({"code": "direct_report_conflict", "severity": "error", "message": msg})
            severity = "error"

        # Check 3: Rating variance bias
        peer_scores = scores_map.get(emp_id, [])
        if len(peer_scores) >= 2:
            avg = sum(peer_scores) / len(peer_scores)
            variance = max(peer_scores) - min(peer_scores)
            if variance > 2.0:
                msg = f"Variance peer rating tinggi: {variance:.1f} poin (avg: {avg:.1f}) — potensi bias"
                emp_issues.append({"code": "high_variance", "severity": "warning", "message": msg,
                                   "variance": round(variance, 2), "avg_peer_score": round(avg, 2)})
                if severity == "ok":
                    severity = "warning"

        if severity == "error":
            errors_count += 1
        elif severity == "warning":
            warnings_count += 1
        else:
            ok_count += 1

        if emp_issues:
            issues.append({
                "employee_id": emp_id,
                "employee_name": emp_name,
                "employee_code": emp_code,
                "reviewer_count": reviewer_count,
                "severity": severity,
                "issues": emp_issues,
            })

    overall_severity = "ok"
    if errors_count > 0:
        overall_severity = "error"
    elif warnings_count > 0:
        overall_severity = "warning"

    return {
        "ok": True,
        "period_id": period_id,
        "period_name": period.get("name", ""),
        "total_participants": len(participant_ids),
        "issues_count": len(issues),
        "errors_count": errors_count,
        "warnings_count": warnings_count,
        "ok_count": ok_count,
        "overall_severity": overall_severity,
        "issues": issues,
        "summary": (
            f"{len(participant_ids)} peserta diperiksa: "
            f"{errors_count} error, {warnings_count} warning, {ok_count} aman."
        ),
    }

