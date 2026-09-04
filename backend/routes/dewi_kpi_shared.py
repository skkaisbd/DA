# ruff: noqa: F401
"""
dewi_kpi_shared.py — Shared Helpers, Models & Constants
Extracted from dewi_kpi.py (2729 LOC monolith)
"""
# ⛔ RETIRED — Session #12 P2: Split into dewi_kpi_{shared,config,perform,results,gamification,analytics,export}.py
# DO NOT add new code here. This file is kept for git history only.
# ruff: noqa
"""
CV. Dewi Aditya — Sistem KPI Karyawan (DA KPI System)

Formula:
  KPI Akhir = (Perform × 60%) + (Attitude × 20%) + (Absensi × 20%)

Attitude (360°):
  = (Self × 20%) + (Peer × 20%) + (Supervisor→Staff × 35%) + (Staff→Supervisor × 25%)
  Konversi: rata_rata(1-5) × 20 = skor 0-100

Absensi:
  = (1 - hari_tidak_hadir/hari_kerja) × 100
  Terlambat = -0.25 hari, Pulang Awal = -0.5 hari, Izin/Sakit/Alfa/Cuti = -1 hari

Grading:
  A (91-100) → Naik Gaji 10%
  B (80-90)  → Save / Perpanjang Kontrak (7%)
  C (75-79)  → Mediasi/Evaluasi
  D (50-69)  → Cut Off
  E (0-49)   → Cut Off

Collections:
  da_kpi_periods       — periode KPI (konfigurasi HR)
  da_kpi_questions     — bank soal (dapat dikonfigurasi HR)
  da_kpi_submissions   — pengisian form per karyawan
  da_kpi_perform       — nilai Perform per karyawan per periode
  da_kpi_results       — hasil KPI final
"""
# ruff: noqa: F401

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Request, HTTPException, Query
from database import get_db
from auth import require_auth
from routes.shared import get_pagination_params, paginated_response

router = APIRouter(prefix="/api/dewi/kpi", tags=["dewi-kpi"])


# ═══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

def _uid():
    return str(uuid.uuid4())

def _now():
    return datetime.now(timezone.utc)

def _s(doc):
    if doc is None:
        return None
    doc = dict(doc)
    doc.pop("_id", None)
    for k, v in doc.items():
        if isinstance(v, datetime):
            doc[k] = v.isoformat()
    return doc

def _grade(score: float):
    if score >= 91:
        return {"grade": "A", "label": "Sangat Baik", "status": "Berhak Naik Gaji", "raise_pct": 10}
    elif score >= 80:
        return {"grade": "B", "label": "Baik", "status": "Save / Perpanjang Kontrak", "raise_pct": 7}
    elif score >= 75:
        return {"grade": "C", "label": "Cukup", "status": "Mediasi / Evaluasi", "raise_pct": 0}
    elif score >= 50:
        return {"grade": "D", "label": "Kurang", "status": "Cut Off", "raise_pct": 0}
    else:
        return {"grade": "E", "label": "Sangat Kurang", "status": "Cut Off", "raise_pct": 0}

async def _require_hr(request: Request):
    user = await require_auth(request)
    role = (user.get("role") or "").lower()
    if role in ("superadmin", "admin", "owner", "hr", "manager", "supervisor"):
        return user
    raise HTTPException(403, "Akses ditolak: butuh role HR/Manager/Supervisor.")

async def _get_linked_employee(db, user: dict):
    """Delegasi ke SSOT `utils.employee_identity.resolve_my_employee` (FASE 15).

    Isi lama (employee_id → user_id → email) dipindah ke SSOT supaya tidak ada
    lagi 4 salinan aturan identitas yang bisa menyimpang satu sama lain.
    """
    from utils.employee_identity import resolve_my_employee
    return await resolve_my_employee(db, user)


# ═══════════════════════════════════════════════════════════════════════════════
# DEFAULT QUESTIONS (SEED)
# ═══════════════════════════════════════════════════════════════════════════════

DEFAULT_QUESTIONS = [
    # ── SELF ASSESSMENT (20%) — 10 kategori × 2 pertanyaan ──────────────────
    {"eval_type": "self", "category": "Tanggung Jawab Kerja", "category_weight": 0.10, "order": 1,
     "question_text": "Saya menyelesaikan tugas yang diberikan sesuai dengan target dan tenggat waktu."},
    {"eval_type": "self", "category": "Tanggung Jawab Kerja", "category_weight": 0.10, "order": 2,
     "question_text": "Saya bertanggung jawab atas hasil kerja saya dan tidak melempar kesalahan pada orang lain."},
    {"eval_type": "self", "category": "Kepatuhan terhadap SOP & Arahan Atasan", "category_weight": 0.10, "order": 3,
     "question_text": "Saya mengikuti SOP dan prosedur kerja yang telah ditetapkan perusahaan."},
    {"eval_type": "self", "category": "Kepatuhan terhadap SOP & Arahan Atasan", "category_weight": 0.10, "order": 4,
     "question_text": "Saya melaksanakan arahan atasan dengan baik dan tepat waktu."},
    {"eval_type": "self", "category": "Sikap terhadap Atasan", "category_weight": 0.10, "order": 5,
     "question_text": "Saya menghormati dan bersikap sopan kepada atasan."},
    {"eval_type": "self", "category": "Sikap terhadap Atasan", "category_weight": 0.10, "order": 6,
     "question_text": "Saya mengkomunikasikan masalah pekerjaan kepada atasan dengan cara yang tepat."},
    {"eval_type": "self", "category": "Kerja Sama Tim", "category_weight": 0.10, "order": 7,
     "question_text": "Saya aktif berkontribusi dalam kerja tim dan membantu rekan yang membutuhkan."},
    {"eval_type": "self", "category": "Kerja Sama Tim", "category_weight": 0.10, "order": 8,
     "question_text": "Saya menempatkan kepentingan tim di atas kepentingan pribadi."},
    {"eval_type": "self", "category": "Sikap terhadap Rekan Kerja", "category_weight": 0.10, "order": 9,
     "question_text": "Saya bersikap respectful dan menghargai rekan kerja saya."},
    {"eval_type": "self", "category": "Sikap terhadap Rekan Kerja", "category_weight": 0.10, "order": 10,
     "question_text": "Saya tidak terlibat dalam gosip atau konflik yang mengganggu suasana kerja."},
    {"eval_type": "self", "category": "Etika & Perilaku Profesional", "category_weight": 0.10, "order": 11,
     "question_text": "Saya berpakaian dan bersikap sesuai dengan standar profesional perusahaan."},
    {"eval_type": "self", "category": "Etika & Perilaku Profesional", "category_weight": 0.10, "order": 12,
     "question_text": "Saya menjaga rahasia perusahaan dan tidak membocorkan informasi internal."},
    {"eval_type": "self", "category": "Loyalitas & Komitmen", "category_weight": 0.10, "order": 13,
     "question_text": "Saya berkomitmen untuk memberikan yang terbaik bagi perusahaan."},
    {"eval_type": "self", "category": "Loyalitas & Komitmen", "category_weight": 0.10, "order": 14,
     "question_text": "Saya tidak mudah menyerah ketika menghadapi tantangan dalam pekerjaan."},
    {"eval_type": "self", "category": "Inisiatif & Kepedulian", "category_weight": 0.10, "order": 15,
     "question_text": "Saya mengambil inisiatif untuk memperbaiki proses kerja tanpa harus selalu diperintah."},
    {"eval_type": "self", "category": "Inisiatif & Kepedulian", "category_weight": 0.10, "order": 16,
     "question_text": "Saya peduli terhadap kebersihan dan ketertiban lingkungan kerja."},
    {"eval_type": "self", "category": "Kematangan Emosi & Sikap Positif", "category_weight": 0.10, "order": 17,
     "question_text": "Saya mengelola emosi dengan baik dan tidak mudah marah di lingkungan kerja."},
    {"eval_type": "self", "category": "Kematangan Emosi & Sikap Positif", "category_weight": 0.10, "order": 18,
     "question_text": "Saya bersikap positif dan menjadi energi yang baik bagi tim."},
    {"eval_type": "self", "category": "Integritas & Kejujuran", "category_weight": 0.10, "order": 19,
     "question_text": "Saya selalu jujur dalam melaporkan hasil kerja dan kondisi aktual."},
    {"eval_type": "self", "category": "Integritas & Kejujuran", "category_weight": 0.10, "order": 20,
     "question_text": "Saya tidak melakukan tindakan yang merugikan perusahaan atau rekan kerja."},

    # ── PEER ASSESSMENT (20%) — 3 kategori ───────────────────────────────────
    {"eval_type": "peer", "category": "Teamwork", "category_weight": 0.40, "order": 1,
     "question_text": "Rekan ini aktif berkontribusi dalam pekerjaan tim dan dapat diandalkan."},
    {"eval_type": "peer", "category": "Teamwork", "category_weight": 0.40, "order": 2,
     "question_text": "Rekan ini membantu anggota tim lain yang kesulitan tanpa diminta."},
    {"eval_type": "peer", "category": "Sikap", "category_weight": 0.30, "order": 3,
     "question_text": "Rekan ini bersikap respectful dan menjaga suasana positif di tempat kerja."},
    {"eval_type": "peer", "category": "Sikap", "category_weight": 0.30, "order": 4,
     "question_text": "Rekan ini tidak terlibat dalam gosip atau perselisihan yang tidak perlu."},
    {"eval_type": "peer", "category": "Komunikasi", "category_weight": 0.30, "order": 5,
     "question_text": "Rekan ini berkomunikasi dengan jelas dan terbuka dalam pekerjaan."},
    {"eval_type": "peer", "category": "Komunikasi", "category_weight": 0.30, "order": 6,
     "question_text": "Rekan ini mendengarkan pendapat orang lain dengan baik."},

    # ── SUPERVISOR TO STAFF (35%) — 6 kategori ───────────────────────────────
    {"eval_type": "supervisor_to_staff", "category": "Tanggung Jawab", "category_weight": 0.20, "order": 1,
     "question_text": "Karyawan menyelesaikan tugas sesuai target dan deadline yang ditetapkan."},
    {"eval_type": "supervisor_to_staff", "category": "Tanggung Jawab", "category_weight": 0.20, "order": 2,
     "question_text": "Karyawan bertanggung jawab penuh atas hasil pekerjaannya."},
    {"eval_type": "supervisor_to_staff", "category": "Kepatuhan terhadap SOP", "category_weight": 0.15, "order": 3,
     "question_text": "Karyawan mengikuti SOP dan prosedur kerja yang berlaku."},
    {"eval_type": "supervisor_to_staff", "category": "Kepatuhan terhadap SOP", "category_weight": 0.15, "order": 4,
     "question_text": "Karyawan melaksanakan arahan dengan baik dan tepat."},
    {"eval_type": "supervisor_to_staff", "category": "Hasil Kerja", "category_weight": 0.20, "order": 5,
     "question_text": "Kualitas hasil kerja karyawan memenuhi standar yang ditetapkan."},
    {"eval_type": "supervisor_to_staff", "category": "Hasil Kerja", "category_weight": 0.20, "order": 6,
     "question_text": "Kuantitas output kerja karyawan sesuai atau melebihi ekspektasi."},
    {"eval_type": "supervisor_to_staff", "category": "Integritas", "category_weight": 0.15, "order": 7,
     "question_text": "Karyawan jujur dan transparan dalam melaporkan pekerjaan."},
    {"eval_type": "supervisor_to_staff", "category": "Integritas", "category_weight": 0.15, "order": 8,
     "question_text": "Karyawan dapat dipercaya dan tidak melakukan tindakan yang merugikan."},
    {"eval_type": "supervisor_to_staff", "category": "Etika & Perilaku Profesional", "category_weight": 0.15, "order": 9,
     "question_text": "Karyawan bersikap profesional dan menjaga nama baik perusahaan."},
    {"eval_type": "supervisor_to_staff", "category": "Etika & Perilaku Profesional", "category_weight": 0.15, "order": 10,
     "question_text": "Karyawan berinteraksi dengan rekan dan atasan secara sopan dan positif."},
    {"eval_type": "supervisor_to_staff", "category": "Inisiatif", "category_weight": 0.15, "order": 11,
     "question_text": "Karyawan menunjukkan inisiatif dan kreativitas dalam menyelesaikan masalah."},
    {"eval_type": "supervisor_to_staff", "category": "Inisiatif", "category_weight": 0.15, "order": 12,
     "question_text": "Karyawan aktif memberikan masukan untuk perbaikan proses kerja."},

    # ── STAFF TO SUPERVISOR (25%) — 2 kategori, ANONIM ───────────────────────
    {"eval_type": "staff_to_supervisor", "category": "Gaya Kepemimpinan", "category_weight": 0.60, "order": 1,
     "question_text": "Atasan saya memberikan arahan yang jelas dan terstruktur kepada tim."},
    {"eval_type": "staff_to_supervisor", "category": "Gaya Kepemimpinan", "category_weight": 0.60, "order": 2,
     "question_text": "Atasan saya adil dalam memberikan penilaian dan perlakuan kepada anggota tim."},
    {"eval_type": "staff_to_supervisor", "category": "Gaya Kepemimpinan", "category_weight": 0.60, "order": 3,
     "question_text": "Atasan saya mendukung pengembangan kemampuan dan karir anggota timnya."},
    {"eval_type": "staff_to_supervisor", "category": "Komunikasi", "category_weight": 0.40, "order": 4,
     "question_text": "Atasan saya berkomunikasi dengan jelas dan terbuka kepada tim."},
    {"eval_type": "staff_to_supervisor", "category": "Komunikasi", "category_weight": 0.40, "order": 5,
     "question_text": "Atasan saya mendengarkan masukan dan keluhan anggota tim dengan serius."},
    {"eval_type": "staff_to_supervisor", "category": "Komunikasi", "category_weight": 0.40, "order": 6,
     "question_text": "Atasan saya memberikan feedback yang konstruktif dan membangun."},
]


# ═══════════════════════════════════════════════════════════════════════════════
# CALCULATION HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

def _calc_section_score(answers: list, questions: list) -> dict:
    """
    Hitung skor section dari jawaban + data pertanyaan.
    Returns: {section_score (0-100), category_breakdown, answered_count, total_count}
    """
    # Build question map
    {q["question_id"]: q for q in questions}
    ans_map = {a["question_id"]: a["score"] for a in answers}

    # Group by category
    categories = {}
    for q in questions:
        cat = q["category"]
        if cat not in categories:
            categories[cat] = {"weight": q["category_weight"], "scores": []}
        if q["question_id"] in ans_map:
            categories[cat]["scores"].append(ans_map[q["question_id"]])

    category_breakdown = []
    section_score = 0.0
    total_weight_with_answers = 0.0

    for cat, data in categories.items():
        if data["scores"]:
            cat_avg_raw = sum(data["scores"]) / len(data["scores"])  # 1-5 scale
            cat_score_100 = min(100.0, cat_avg_raw * 20)  # convert to 0-100
            section_score += cat_score_100 * data["weight"]
            total_weight_with_answers += data["weight"]
        else:
            cat_score_100 = 0.0
        category_breakdown.append({
            "category": cat,
            "weight": data["weight"],
            "avg_raw": round(sum(data["scores"]) / len(data["scores"]), 2) if data["scores"] else None,
            "score_100": round(cat_score_100, 2),
            "answered": len(data["scores"]),
        })

    # Normalize if not all categories answered
    if total_weight_with_answers > 0 and total_weight_with_answers < 1.0:
        section_score = section_score / total_weight_with_answers

    answered_count = sum(1 for a in answers if a.get("score") is not None)
    total_count = len(questions)

    return {
        "section_score": round(min(100.0, max(0.0, section_score)), 2),
        "category_breakdown": category_breakdown,
        "answered_count": answered_count,
        "total_count": total_count,
    }


async def _calc_attitude_score(db, period_id: str, employee_id: str) -> dict:
    """
    Hitung attitude score karyawan dari semua submission yang terkait.
    """
    # Get all questions
    all_q = await db.da_kpi_questions.find({"is_active": True}, {"_id": 0}).to_list(500)
    q_by_type = {}
    for q in all_q:
        et = q["eval_type"]
        if et not in q_by_type:
            q_by_type[et] = []
        q_by_type[et].append(q)

    scores = {}
    breakdowns = {}
    status_detail = {}

    # Self (evaluator = evaluatee = employee)
    self_sub = await db.da_kpi_submissions.find_one(
        {"period_id": period_id, "evaluatee_id": employee_id, "eval_type": "self", "status": "submitted"},
        {"_id": 0}
    )
    if self_sub:
        calc = _calc_section_score(self_sub.get("answers", []), q_by_type.get("self", []))
        scores["self"] = calc["section_score"]
        breakdowns["self"] = calc["category_breakdown"]
        status_detail["self"] = "submitted"
    else:
        scores["self"] = None
        status_detail["self"] = "pending"

    # Peer (multiple submissions → average)
    peer_subs = await db.da_kpi_submissions.find(
        {"period_id": period_id, "evaluatee_id": employee_id, "eval_type": "peer", "status": "submitted"},
        {"_id": 0}
    ).to_list(500)
    if peer_subs:
        peer_scores_list = []
        for ps in peer_subs:
            calc = _calc_section_score(ps.get("answers", []), q_by_type.get("peer", []))
            peer_scores_list.append(calc["section_score"])
        scores["peer"] = round(sum(peer_scores_list) / len(peer_scores_list), 2)
        status_detail["peer"] = f"submitted ({len(peer_subs)} penilai)"
    else:
        scores["peer"] = None
        status_detail["peer"] = "pending"

    # Supervisor to Staff (multiple supervisors possible → average)
    sup_subs = await db.da_kpi_submissions.find(
        {"period_id": period_id, "evaluatee_id": employee_id, "eval_type": "supervisor_to_staff", "status": "submitted"},
        {"_id": 0}
    ).to_list(500)
    if sup_subs:
        sup_scores_list = []
        for ss in sup_subs:
            calc = _calc_section_score(ss.get("answers", []), q_by_type.get("supervisor_to_staff", []))
            sup_scores_list.append(calc["section_score"])
        scores["supervisor_to_staff"] = round(sum(sup_scores_list) / len(sup_scores_list), 2)
        status_detail["supervisor_to_staff"] = f"submitted ({len(sup_subs)} supervisor)"
    else:
        scores["supervisor_to_staff"] = None
        status_detail["supervisor_to_staff"] = "pending"

    # Staff to Supervisor (evaluatee = supervisor, but we look by period & employee)
    # Find period to get supervisor assignment
    period = await db.da_kpi_periods.find_one({"period_id": period_id}, {"_id": 0})
    sup_assignments = period.get("supervisor_assignments", []) if period else []
    # Find which supervisor this employee is assigned to
    my_supervisor_id = None
    for sa in sup_assignments:
        if employee_id in sa.get("employee_ids", []):
            my_supervisor_id = sa.get("supervisor_employee_id")
            break

    staff_sub = None
    if my_supervisor_id:
        staff_sub = await db.da_kpi_submissions.find_one(
            {"period_id": period_id, "evaluator_id": employee_id,
             "evaluatee_id": my_supervisor_id, "eval_type": "staff_to_supervisor", "status": "submitted"},
            {"_id": 0}
        )
    if staff_sub:
        calc = _calc_section_score(staff_sub.get("answers", []), q_by_type.get("staff_to_supervisor", []))
        scores["staff_to_supervisor"] = calc["section_score"]
        breakdowns["staff_to_supervisor"] = calc["category_breakdown"]
        status_detail["staff_to_supervisor"] = "submitted"
    else:
        scores["staff_to_supervisor"] = None
        status_detail["staff_to_supervisor"] = "pending" if my_supervisor_id else "no_supervisor_assigned"

    # Compute weighted attitude score (use available scores, normalize weights)
    weights = {"self": 0.20, "peer": 0.20, "supervisor_to_staff": 0.35, "staff_to_supervisor": 0.25}
    filled_weight = sum(weights[k] for k, v in scores.items() if v is not None)
    attitude_score = None
    if filled_weight > 0:
        weighted_sum = sum(scores[k] * weights[k] for k in scores if scores[k] is not None)
        attitude_score = round(weighted_sum / filled_weight, 2)

    return {
        "attitude_score": attitude_score,
        "component_scores": scores,
        "weights": weights,
        "breakdowns": breakdowns,
        "status_detail": status_detail,
        "is_complete": all(v is not None for v in scores.values()),
    }


async def _calc_absensi_score(db, period_id: str, employee_id: str) -> dict:
    """
    Hitung absensi score dari data attendance.
    """
    period = await db.da_kpi_periods.find_one({"period_id": period_id}, {"_id": 0})
    if not period:
        return {"absensi_score": None, "detail": {}}

    period_from = period.get("period_from")
    period_to = period.get("period_to")
    working_days = int(period.get("working_days") or 26)

    if not period_from or not period_to:
        return {"absensi_score": None, "detail": {"error": "Tanggal periode belum diatur"}}

    # Query attendance
    att_records = await db.rahaza_attendance_events.find(
        {"employee_id": employee_id, "date": {"$gte": period_from, "$lte": period_to}},
        {"_id": 0, "status": 1, "date": 1}
    ).to_list(500)

    absent_days = 0.0
    breakdown = {"izin": 0, "sakit": 0, "alfa": 0, "cuti": 0, "terlambat": 0, "pulang_awal": 0}

    for r in att_records:
        s = (r.get("status") or "hadir").lower()
        if s in ("izin",):
            absent_days += 1.0
            breakdown["izin"] += 1
        elif s in ("sakit",):
            absent_days += 1.0
            breakdown["sakit"] += 1
        elif s in ("alfa", "alpha", "alpa"):
            absent_days += 1.0
            breakdown["alfa"] += 1
        elif s in ("cuti",):
            absent_days += 1.0
            breakdown["cuti"] += 1
        elif s in ("terlambat",):
            absent_days += 0.25
            breakdown["terlambat"] += 1
        elif s in ("pulang_awal",):
            absent_days += 0.5
            breakdown["pulang_awal"] += 1

    score = max(0.0, min(100.0, (1 - absent_days / working_days) * 100))

    return {
        "absensi_score": round(score, 2),
        "absent_days": round(absent_days, 2),
        "working_days": working_days,
        "attendance_record_count": len(att_records),
        "breakdown": breakdown,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# PERIOD MANAGEMENT (HR ADMIN)
# ═══════════════════════════════════════════════════════════════════════════════


# ═══════════════════════════════════════════════════════════════════════════════
# GAMIFICATION — BADGE DEFINITIONS & AWARDING
# (Moved here from dewi_kpi_results.py for cross-module reuse)
# ═══════════════════════════════════════════════════════════════════════════════

BADGE_DEFS = {
    "gold_medal":     {"label": "Juara 1",          "emoji": "🥇", "color": "#F59E0B", "desc": "Ranking #1 pada periode KPI"},
    "silver_medal":   {"label": "Juara 2",          "emoji": "🥈", "color": "#9CA3AF", "desc": "Ranking #2 pada periode KPI"},
    "bronze_medal":   {"label": "Juara 3",          "emoji": "🥉", "color": "#B45309", "desc": "Ranking #3 pada periode KPI"},
    "perfect_score":  {"label": "Nilai Sempurna",   "emoji": "⭐", "color": "#7C3AED", "desc": "KPI Final ≥ 95"},
    "grade_a":        {"label": "Grade A",          "emoji": "💎", "color": "#0EA5E9", "desc": "KPI Grade A (91–100)"},
    "most_improved":  {"label": "Paling Meningkat", "emoji": "📈", "color": "#10B981", "desc": "Peningkatan skor terbesar dari periode sebelumnya"},
    "consistent_top": {"label": "Konsisten Terbaik","emoji": "🔥", "color": "#EF4444", "desc": "Masuk Top 3 pada 3+ periode berturut-turut"},
    "goal_crusher":   {"label": "Goal Achiever",    "emoji": "🎯", "color": "#8B5CF6", "desc": "Semua target KPI tercapai dalam periode"},
    "top_performer":  {"label": "Top Performer",    "emoji": "💪", "color": "#F97316", "desc": "KPI Final ≥ 90"},
}


async def _calculate_and_award_badges(db, period_id: str) -> dict:
    """
    Hitung dan berikan badge setelah KPI dipublish.
    Idempotent — hapus badge lama untuk period ini, lalu recalculate.
    """
    results = await db.da_kpi_results.find(
        {"period_id": period_id, "kpi_final": {"$ne": None}},
        {"_id": 0}
    ).to_list(500)

    if not results:
        return {"awarded": 0}

    # Hapus badge lama untuk period ini (idempotent)
    await db.da_kpi_badges.delete_many({"period_id": period_id})

    sorted_results = sorted(results, key=lambda r: float(r.get("kpi_final") or 0), reverse=True)

    badges_to_insert = []
    now = datetime.now(timezone.utc)

    # Rank badges
    rank_badges = {0: "gold_medal", 1: "silver_medal", 2: "bronze_medal"}
    for i, r in enumerate(sorted_results[:3]):
        if float(r.get("kpi_final") or 0) > 0:
            btype = rank_badges[i]
            badges_to_insert.append({
                "id": str(uuid.uuid4()),
                "employee_id": r["employee_id"],
                "employee_name": r.get("employee_name", ""),
                "employee_code": r.get("employee_code", ""),
                "period_id": period_id,
                "badge_type": btype,
                "badge_label": BADGE_DEFS[btype]["label"],
                "badge_emoji": BADGE_DEFS[btype]["emoji"],
                "rank": i + 1,
                "score": float(r.get("kpi_final") or 0),
                "earned_at": now,
            })

    # Score-based badges
    for r in results:
        score = float(r.get("kpi_final") or 0)
        emp_id = r["employee_id"]
        emp_name = r.get("employee_name", "")
        emp_code = r.get("employee_code", "")

        if score >= 95:
            badges_to_insert.append({
                "id": str(uuid.uuid4()),
                "employee_id": emp_id, "employee_name": emp_name, "employee_code": emp_code,
                "period_id": period_id, "badge_type": "perfect_score",
                "badge_label": BADGE_DEFS["perfect_score"]["label"],
                "badge_emoji": BADGE_DEFS["perfect_score"]["emoji"],
                "rank": None, "score": score, "earned_at": now,
            })
        if score >= 90:
            badges_to_insert.append({
                "id": str(uuid.uuid4()),
                "employee_id": emp_id, "employee_name": emp_name, "employee_code": emp_code,
                "period_id": period_id, "badge_type": "top_performer",
                "badge_label": BADGE_DEFS["top_performer"]["label"],
                "badge_emoji": BADGE_DEFS["top_performer"]["emoji"],
                "rank": None, "score": score, "earned_at": now,
            })
        if r.get("grade") == "A":
            badges_to_insert.append({
                "id": str(uuid.uuid4()),
                "employee_id": emp_id, "employee_name": emp_name, "employee_code": emp_code,
                "period_id": period_id, "badge_type": "grade_a",
                "badge_label": BADGE_DEFS["grade_a"]["label"],
                "badge_emoji": BADGE_DEFS["grade_a"]["emoji"],
                "rank": None, "score": score, "earned_at": now,
            })

    # Most improved — compare with previous period
    prev_results = await db.da_kpi_results.find(
        {"period_id": {"$ne": period_id}, "kpi_final": {"$ne": None}},
        {"_id": 0, "employee_id": 1, "kpi_final": 1, "period_id": 1}
    ).sort("earned_at", -1).to_list(500)

    prev_map: dict = {}
    for pr in prev_results:
        eid = pr["employee_id"]
        if eid not in prev_map:
            prev_map[eid] = float(pr.get("kpi_final") or 0)

    best_improvement = 0
    best_emp = None
    for r in results:
        eid = r["employee_id"]
        curr = float(r.get("kpi_final") or 0)
        prev = prev_map.get(eid)
        if prev is not None:
            improvement = curr - prev
            if improvement > best_improvement:
                best_improvement = improvement
                best_emp = r

    if best_emp and best_improvement > 0:
        badges_to_insert.append({
            "id": str(uuid.uuid4()),
            "employee_id": best_emp["employee_id"],
            "employee_name": best_emp.get("employee_name", ""),
            "employee_code": best_emp.get("employee_code", ""),
            "period_id": period_id, "badge_type": "most_improved",
            "badge_label": BADGE_DEFS["most_improved"]["label"],
            "badge_emoji": BADGE_DEFS["most_improved"]["emoji"],
            "rank": None, "score": float(best_emp.get("kpi_final") or 0),
            "score_improvement": round(best_improvement, 1), "earned_at": now,
        })

    # Consistent top — count periods where employee was top 3
    all_periods_results = await db.da_kpi_results.find(
        {"kpi_final": {"$ne": None}}, {"_id": 0}
    ).to_list(500)

    from collections import defaultdict
    periods_per_emp: dict = defaultdict(list)
    for r in all_periods_results:
        periods_per_emp[r["employee_id"]].append(r)

    for emp_id, emp_results in periods_per_emp.items():
        top3_periods = 0
        for per_id in set(r["period_id"] for r in emp_results):
            per_res = [r for r in all_periods_results if r["period_id"] == per_id]
            per_sorted = sorted(per_res, key=lambda x: float(x.get("kpi_final") or 0), reverse=True)
            top3_ids = [r["employee_id"] for r in per_sorted[:3]]
            if emp_id in top3_ids:
                top3_periods += 1
        if top3_periods >= 3:
            emp_r = next((r for r in emp_results if r["period_id"] == period_id), None)
            if emp_r:
                badges_to_insert.append({
                    "id": str(uuid.uuid4()),
                    "employee_id": emp_id,
                    "employee_name": emp_r.get("employee_name", ""),
                    "employee_code": emp_r.get("employee_code", ""),
                    "period_id": period_id, "badge_type": "consistent_top",
                    "badge_label": BADGE_DEFS["consistent_top"]["label"],
                    "badge_emoji": BADGE_DEFS["consistent_top"]["emoji"],
                    "rank": None, "score": float(emp_r.get("kpi_final") or 0),
                    "top3_count": top3_periods, "earned_at": now,
                })

    if badges_to_insert:
        await db.da_kpi_badges.insert_many(badges_to_insert)

    try:
        await db.da_kpi_badges.create_index([("employee_id", 1), ("earned_at", -1)])
        await db.da_kpi_badges.create_index([("period_id", 1), ("badge_type", 1)])
        await db.da_kpi_badges.create_index("badge_type")
    except Exception:
        logging.getLogger(__name__).debug("suppressed exception", exc_info=True)

    return {"awarded": len(badges_to_insert)}
