"""
Session 15 — P2-8, P2-9, P2-10: HR AI Features

P2-8: AI Resume Screening
- POST /api/hr/ai/resume-screen/{candidate_id}  — AI screens candidate resume
- GET  /api/hr/ai/resume-screen/history          — History of screenings

P2-9: Predictive Attrition
- POST /api/hr/ai/attrition/predict              — Predict attrition risk
- GET  /api/hr/ai/attrition/dashboard            — Attrition risk dashboard

P2-10: Performance Coaching AI
- POST /api/hr/ai/coaching/{employee_id}         — Generate coaching plan
- GET  /api/hr/ai/coaching/history               — Coaching history
"""
import os
import uuid
import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, List
from fastapi import APIRouter, Request, Query, HTTPException
from pydantic import BaseModel, Field
from database import get_db
from auth import require_auth
from ai_llm import LlmChat, UserMessage

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/hr/ai", tags=["hr-ai"])

LLM_KEY   = os.environ.get("EMERGENT_LLM_KEY", "")
LLM_MODEL = ("openai", "gpt-5.1")


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

async def _call_ai(system_msg: str, user_msg: str, tag: str) -> str:
    if not LLM_KEY:
        raise HTTPException(500, "EMERGENT_LLM_KEY tidak dikonfigurasi")
    chat = LlmChat(
        api_key=LLM_KEY,
        session_id=f"hr-ai-{tag}-{uuid.uuid4().hex[:8]}",
        system_message=system_msg,
    ).with_model(*LLM_MODEL)
    return await chat.send_message(UserMessage(text=user_msg))

def _parse_json_response(text: str) -> dict:
    try:
        start = text.find("{")
        end   = text.rfind("}") + 1
        if start >= 0 and end > start:
            return json.loads(text[start:end])
    except Exception:
        logging.getLogger(__name__).debug("suppressed exception", exc_info=True)
    return {"raw_response": text}


# ═══════════════════════════════════════════════════════════════════════
#  P2-8: AI RESUME SCREENING
# ═══════════════════════════════════════════════════════════════════════

class ResumeScreenRequest(BaseModel):
    job_requirements: Optional[str] = Field(default="", description="Deskripsi persyaratan posisi")
    focus_areas: Optional[List[str]] = Field(default_factory=list, description="Area yang ingin difokuskan: skills, experience, education")


@router.post("/resume-screen/{candidate_id}")
async def screen_resume(
    candidate_id: str,
    payload: ResumeScreenRequest,
    request: Request,
):
    """
    P2-8: AI Resume Screening.
    Analisis profil kandidat vs. persyaratan posisi, berikan skor dan rekomendasi.
    """
    await require_auth(request)
    db = get_db()

    # Get candidate data
    candidate = await db.dewi_recruitment_candidates.find_one(
        {"candidate_id": candidate_id}, {"_id": 0}
    )
    if not candidate:
        raise HTTPException(404, "Kandidat tidak ditemukan")

    # Get job info
    job = None
    if candidate.get("job_id"):
        job = await db.dewi_recruitment_jobs.find_one(
            {"job_id": candidate["job_id"]}, {"_id": 0}
        )

    candidate_profile = {
        "name": candidate.get("name"),
        "position_applied": candidate.get("position_applied"),
        "experience_years": candidate.get("experience_years"),
        "education": candidate.get("education"),
        "skills": candidate.get("skills", []),
        "cv_text": candidate.get("cv_text", ""),
        "current_stage": candidate.get("stage", ""),
        "source": candidate.get("source", ""),
    }

    job_info = {}
    if job:
        job_info = {
            "title": job.get("title"),
            "department": job.get("department"),
            "requirements": job.get("requirements", []),
            "description": job.get("description", ""),
        }

    system_prompt = """Kamu adalah AI HR Recruiter untuk CV. Dewi Aditya.
Analisis profil kandidat dan berikan penilaian objektif untuk posisi yang dilamar.
Format JSON response:
{
  "overall_score": 85,
  "recommendation": "Strongly Recommended / Recommended / Consider / Not Recommended",
  "strengths": ["strength 1", "strength 2", "strength 3"],
  "weaknesses": ["weakness 1", "weakness 2"],
  "skill_match": [{"skill": "", "match": "yes/partial/no", "notes": ""}],
  "experience_assessment": "penilaian pengalaman",
  "education_assessment": "penilaian pendidikan",
  "culture_fit": "high/medium/low",
  "interview_questions": ["pertanyaan 1 untuk interview", "pertanyaan 2"],
  "summary": "ringkasan penilaian keseluruhan"
}"""

    user_prompt = f"""Profil Kandidat:\n{json.dumps(candidate_profile, ensure_ascii=False, indent=2)}

Info Posisi:\n{json.dumps(job_info, ensure_ascii=False, indent=2)}

Persyaratan Tambahan: {payload.job_requirements or 'Tidak ada'}
Fokus Area: {', '.join(payload.focus_areas) if payload.focus_areas else 'Semua area'}"""

    raw = await _call_ai(system_prompt, user_prompt, "resume-screen")
    analysis = _parse_json_response(raw)

    # Save to DB
    doc = {
        "id": str(uuid.uuid4()),
        "type": "resume_screening",
        "candidate_id": candidate_id,
        "candidate_name": candidate.get("name"),
        "position": candidate.get("position_applied"),
        "analysis": analysis,
        "generated_at": _now().isoformat(),
    }
    await db.hr_ai_results.insert_one(doc)

    # Update candidate with AI score
    if "overall_score" in analysis:
        await db.dewi_recruitment_candidates.update_one(
            {"candidate_id": candidate_id},
            {"$set": {"ai_score": analysis["overall_score"], "ai_recommendation": analysis.get("recommendation")}}
        )

    return ok(data={"analysis": analysis, "candidate": serialize(candidate_profile), "generated_at": doc["generated_at"]})


@router.get("/resume-screen/history")
async def get_screening_history(request: Request, limit: int = Query(20, ge=1, le=200)):
    await require_auth(request)
    db = get_db()
    docs = await db.hr_ai_results.find({"type": "resume_screening"}, {"_id": 0}).sort("generated_at", -1).limit(limit).to_list(limit)
    return ok(data=serialize(docs))


# ═══════════════════════════════════════════════════════════════════════
#  P2-9: PREDICTIVE ATTRITION
# ═══════════════════════════════════════════════════════════════════════

@router.post("/attrition/predict")
async def predict_attrition(
    request: Request,
    department: Optional[str] = Query(None, description="Filter by department"),
):
    """
    P2-9: Predictive Attrition.
    Analisis faktor risiko resign untuk semua karyawan aktif.
    """
    await require_auth(request)
    db = get_db()

    query = {"employment_status": "active"}
    if department:
        query["department"] = department

    employees = await db.rahaza_employees.find(query, {"_id": 0}).to_list(200)
    if not employees:
        return ok(data=[], meta={"total": 0})

    # For each employee, gather attrition indicators
    emp_data = []
    for emp in employees:
        emp_id = emp.get("id") or emp.get("employee_code")

        # Count absence days (last 90 days) — RC-01/K6: SSOT events; status nyata
        # hanya hadir/izin/sakit → "absence" = izin+sakit
        since90 = _now() - timedelta(days=90)
        absence_count = await db.rahaza_attendance_events.count_documents({
            "employee_id": emp_id,
            "status": {"$in": ["izin", "sakit"]},
            "date": {"$gte": since90.strftime("%Y-%m-%d")}
        })

        # Count late arrivals — K1: is_late tak tersedia di data (shift_id kosong);
        # hitung hanya bila field is_late True (jujur 0 bila tak ada, JANGAN mengarang)
        late_count = await db.rahaza_attendance_events.count_documents({
            "employee_id": emp_id,
            "is_late": True,
            "date": {"$gte": since90.strftime("%Y-%m-%d")}
        })

        # Get leave requests (last 6 months)
        since180 = _now() - timedelta(days=180)
        leave_count = await db.rahaza_leave_requests.count_documents({
            "employee_id": emp_id,
            "created_at": {"$gte": since180.isoformat()}
        })

        # Years of service
        join_date = emp.get("join_date", "")
        years_service = 0
        if join_date:
            try:
                jd = datetime.strptime(str(join_date)[:10], "%Y-%m-%d")
                years_service = round((_now() - jd.replace(tzinfo=timezone.utc)).days / 365, 1)
            except Exception:
                logging.getLogger(__name__).debug("suppressed exception", exc_info=True)

        emp_data.append({
            "employee_id": emp_id,
            "name": emp.get("name"),
            "department": emp.get("department"),
            "job_title": emp.get("job_title"),
            "grade": emp.get("grade"),
            "years_service": years_service,
            "absence_90d": absence_count,
            "late_90d": late_count,
            "leave_requests_6m": leave_count,
            "base_salary": emp.get("base_rate", 0),
        })

    system_prompt = """Kamu adalah AI People Analytics specialist untuk CV. Dewi Aditya.
Analisis data karyawan dan prediksi risiko attrition (resign) untuk setiap karyawan.
Format JSON response:
{
  "employees": [
    {
      "employee_id": "",
      "name": "",
      "risk_level": "high/medium/low",
      "risk_score": 75,
      "risk_factors": ["faktor 1", "faktor 2"],
      "retention_suggestions": ["saran 1", "saran 2"]
    }
  ],
  "department_summary": [{"department": "", "avg_risk": 0.0, "high_risk_count": 0}],
  "overall_insights": "narasi insight keseluruhan",
  "priority_actions": ["aksi prioritas 1", "aksi prioritas 2"]
}"""

    user_prompt = f"Data karyawan aktif:\n{json.dumps(emp_data[:10], ensure_ascii=False, indent=2)}"

    raw = await _call_ai(system_prompt, user_prompt, "attrition")
    analysis = _parse_json_response(raw)

    # Save to DB
    doc = {
        "id": str(uuid.uuid4()),
        "type": "attrition_prediction",
        "department": department,
        "employee_count": len(emp_data),
        "analysis": analysis,
        "generated_at": _now().isoformat(),
    }
    await db.hr_ai_results.insert_one(doc)

    return ok(data={"analysis": analysis, "raw_employee_data": emp_data[:10], "generated_at": doc["generated_at"]})


@router.get("/attrition/dashboard")
async def get_attrition_dashboard(request: Request, limit: int = Query(5, ge=1, le=200)):
    """Get latest attrition predictions."""
    await require_auth(request)
    db = get_db()
    docs = await db.hr_ai_results.find({"type": "attrition_prediction"}, {"_id": 0}).sort("generated_at", -1).limit(limit).to_list(limit)
    return ok(data=serialize(docs))


# ═══════════════════════════════════════════════════════════════════════
#  P2-10: PERFORMANCE COACHING AI
# ═══════════════════════════════════════════════════════════════════════

class CoachingRequest(BaseModel):
    focus: Optional[str] = Field(default="overall", description="Fokus coaching: performance, leadership, technical, communication, time_management")
    goals: Optional[str] = Field(default="", description="Tujuan spesifik yang ingin dicapai")


@router.post("/coaching/{employee_id}")
async def generate_coaching_plan(
    employee_id: str,
    payload: CoachingRequest,
    request: Request,
):
    """
    P2-10: AI Performance Coaching Plan.
    Generate personalized coaching plan berdasarkan data kinerja karyawan.
    """
    await require_auth(request)
    db = get_db()

    # Get employee
    employee = await db.rahaza_employees.find_one(
        {"$or": [{"id": employee_id}, {"employee_code": employee_id}]}, {"_id": 0, "password": 0}
    )
    if not employee:
        raise HTTPException(404, "Karyawan tidak ditemukan")

    emp_id = employee.get("id") or employee.get("employee_code")

    # Get latest performance review
    latest_review = await db.hris_reviews.find_one(
        {"employee_id": emp_id}, sort=[("submitted_at", -1)]
    )

    # Get attendance summary (last 3 months) — RC-01/K6: SSOT events; status nyata hadir/izin/sakit
    since90 = _now() - timedelta(days=90)
    att_total = await db.rahaza_attendance_events.count_documents({"employee_id": emp_id, "date": {"$gte": since90.strftime("%Y-%m-%d")}})
    att_late  = await db.rahaza_attendance_events.count_documents({"employee_id": emp_id, "is_late": True, "date": {"$gte": since90.strftime("%Y-%m-%d")}})
    att_absent= await db.rahaza_attendance_events.count_documents({"employee_id": emp_id, "status": {"$in": ["izin", "sakit"]}, "date": {"$gte": since90.strftime("%Y-%m-%d")}})

    # Get completed training
    trainings = await db.hris_training_completions.find(
        {"employee_id": emp_id}, {"_id": 0, "training_name": 1, "score": 1, "completed_at": 1}
    ).sort("completed_at", -1).limit(5).to_list(5)

    profile = {
        "name": employee.get("name"),
        "job_title": employee.get("job_title"),
        "department": employee.get("department"),
        "grade": employee.get("grade"),
        "years_service": 0,
        "performance_scores": {
            "latest_score": latest_review.get("final_score") if latest_review else None,
            "criteria_scores": latest_review.get("criteria_scores", {}) if latest_review else {},
        } if latest_review else None,
        "attendance": {"total_days_90d": att_total, "late_days": att_late, "absent_days": att_absent},
        "completed_trainings": len(trainings),
        "focus_area": payload.focus,
        "goals": payload.goals,
    }

    # Years of service
    join_date = employee.get("join_date", "")
    if join_date:
        try:
            jd = datetime.strptime(str(join_date)[:10], "%Y-%m-%d")
            profile["years_service"] = round((_now() - jd.replace(tzinfo=timezone.utc)).days / 365, 1)
        except Exception:
            logging.getLogger(__name__).debug("suppressed exception", exc_info=True)

    system_prompt = """Kamu adalah AI Performance Coach untuk CV. Dewi Aditya.
Buat rencana coaching personal yang spesifik, actionable, dan realistis untuk karyawan.
Format JSON:
{
  "coaching_title": "Judul program coaching",
  "employee_summary": "ringkasan profil dan situasi karyawan",
  "key_development_areas": ["area 1", "area 2", "area 3"],
  "smart_goals": [
    {"goal": "", "timeline": "30/60/90 hari", "measurement": "cara mengukur"}
  ],
  "weekly_actions": ["aksi minggu 1", "aksi minggu 2", "aksi minggu 3", "aksi minggu 4"],
  "recommended_trainings": ["training 1", "training 2"],
  "manager_support": "apa yang perlu dilakukan manager",
  "milestones": [{"month": 1, "target": ""}, {"month": 2, "target": ""}, {"month": 3, "target": ""}],
  "motivational_message": "pesan motivasi personal"
}"""

    user_prompt = f"Profil karyawan:\n{json.dumps(profile, ensure_ascii=False, indent=2)}"

    raw = await _call_ai(system_prompt, user_prompt, "coaching")
    plan = _parse_json_response(raw)

    # Save to DB
    doc = {
        "id": str(uuid.uuid4()),
        "type": "coaching_plan",
        "employee_id": emp_id,
        "employee_name": employee.get("name"),
        "focus": payload.focus,
        "plan": plan,
        "generated_at": _now().isoformat(),
    }
    await db.hr_ai_results.insert_one(doc)

    return ok(data={"plan": plan, "employee": {
        "name": employee.get("name"),
        "job_title": employee.get("job_title"),
        "department": employee.get("department"),
    }, "generated_at": doc["generated_at"]})


@router.get("/coaching/history")
async def get_coaching_history(request: Request, employee_id: Optional[str] = None, limit: int = Query(20, ge=1, le=200)):
    await require_auth(request)
    db = get_db()
    query = {"type": "coaching_plan"}
    if employee_id:
        query["employee_id"] = employee_id
    docs = await db.hr_ai_results.find(query, {"_id": 0}).sort("generated_at", -1).limit(limit).to_list(limit)
    return ok(data=serialize(docs))


# ═══════════════════════════════════════════════════════════════════════
#  HELPER: List employees (for dropdowns)
# ═══════════════════════════════════════════════════════════════════════

@router.get("/employees/list")
async def list_employees_for_ai(request: Request):
    """List active employees for dropdown selectors in AI modules."""
    await require_auth(request)
    db = get_db()
    emps = await db.rahaza_employees.find(
        {"employment_status": "active"},
        {"_id": 0, "id": 1, "employee_code": 1, "name": 1, "department": 1, "job_title": 1, "grade": 1}
    ).sort("name", 1).to_list(200)
    return ok(data=serialize(emps))
