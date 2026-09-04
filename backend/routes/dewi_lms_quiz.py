"""
CV. Dewi Aditya — LMS Quiz + Progress + Certificate (Phase 9.5 P2)

Extends dewi_lms.py with:
- Quiz model (questions, passing score)
- Course completion tracking per enrollment
- Auto-generate certificate PDF on pass

Collection: dewi_lms_quizzes
  { quiz_id, course_id, title, passing_score, questions: [
      { question_id, text, options: [str], correct_index, points }
    ]}

Collection: dewi_lms_attempts
  { attempt_id, quiz_id, course_id, employee_id, enrollment_id,
    answers: [int], score, passed, attempted_at }

Field on dewi_lms_enrollments:
  { progress_pct: 0-100, completed_at, certificate_issued }
"""
import uuid
import io
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import StreamingResponse
from database import get_db
from auth import require_auth

router = APIRouter(prefix="/api/dewi/lms", tags=["dewi-lms-quiz"])


def _uid(): return str(uuid.uuid4())
def _now(): return datetime.now(timezone.utc)
def _s(d):
    if not d:
        return None
    d = dict(d)
    d.pop("_id", None)
    for k, v in d.items():
        if isinstance(v, datetime):
            d[k] = v.isoformat()
    return d


# ─── QUIZ CRUD ───────────────────────────────────────────────────────────────

@router.post("/quizzes")
async def create_quiz(request: Request):
    await require_auth(request)
    db = get_db()
    body = await request.json()
    doc = {
        "quiz_id": _uid(),
        "course_id": body.get("course_id"),
        "title": body.get("title") or "Quiz",
        "description": body.get("description") or "",
        "passing_score": int(body.get("passing_score") or 70),
        "questions": body.get("questions") or [],
        "total_points": sum((q.get("points") or 1) for q in (body.get("questions") or [])),
        "is_active": True,
        "created_at": _now(),
        "updated_at": _now(),
    }
    await db.dewi_lms_quizzes.insert_one(doc)
    return {"ok": True, "quiz": _s(doc)}


@router.get("/quizzes")
async def list_quizzes(request: Request, course_id: Optional[str] = None):
    await require_auth(request)
    db = get_db()
    filt = {"is_active": True}
    if course_id:
        filt["course_id"] = course_id
    docs = await db.dewi_lms_quizzes.find(filt, {"_id": 0}).to_list(500)
    return {"ok": True, "quizzes": [_s(d) for d in docs]}


@router.get("/quizzes/{quiz_id}/take")
async def get_quiz_for_attempt(quiz_id: str, request: Request):
    """Return quiz WITHOUT correct answers (for taking)."""
    await require_auth(request)
    db = get_db()
    doc = await db.dewi_lms_quizzes.find_one({"quiz_id": quiz_id}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Quiz tidak ditemukan.")
    # Strip correct_index
    stripped = _s(doc)
    stripped["questions"] = [{k: v for k, v in q.items() if k != "correct_index"} for q in stripped.get("questions", [])]
    return {"ok": True, "quiz": stripped}


@router.post("/quizzes/{quiz_id}/submit")
async def submit_quiz(quiz_id: str, request: Request):
    """Submit answers, calculate score, issue certificate if passed."""
    user = await require_auth(request)
    db = get_db()
    body = await request.json()
    answers = body.get("answers") or []  # list of ints (option index per question)

    quiz = await db.dewi_lms_quizzes.find_one({"quiz_id": quiz_id}, {"_id": 0})
    if not quiz:
        raise HTTPException(404, "Quiz tidak ditemukan.")

    # Score
    earned = 0
    total = quiz.get("total_points", 0) or len(quiz.get("questions", []))
    for idx, q in enumerate(quiz.get("questions", [])):
        given = answers[idx] if idx < len(answers) else -1
        if given == q.get("correct_index"):
            earned += q.get("points", 1)
    pct = round(earned / total * 100) if total > 0 else 0
    passed = pct >= quiz.get("passing_score", 70)

    attempt = {
        "attempt_id": _uid(),
        "quiz_id": quiz_id,
        "course_id": quiz.get("course_id"),
        "employee_id": user.get("employee_id") or body.get("employee_id"),
        "employee_name": user.get("name", ""),
        "enrollment_id": body.get("enrollment_id"),
        "answers": answers,
        "score": earned,
        "total_points": total,
        "score_pct": pct,
        "passed": passed,
        "attempted_at": _now(),
    }
    await db.dewi_lms_attempts.insert_one(attempt)

    # Update enrollment progress
    if body.get("enrollment_id"):
        enroll_upd = {
            "last_quiz_score": pct,
            "last_quiz_passed": passed,
            "updated_at": _now(),
        }
        if passed:
            enroll_upd["progress_pct"] = 100
            enroll_upd["completed_at"] = _now()
            enroll_upd["certificate_issued"] = True
            enroll_upd["certificate_id"] = _uid()
        await db.dewi_lms_enrollments.update_one(
            {"enrollment_id": body["enrollment_id"]}, {"$set": enroll_upd}
        )

    return {"ok": True, "attempt": _s(attempt), "passed": passed, "score_pct": pct}


@router.post("/enrollments/{enrollment_id}/progress")
async def update_progress(enrollment_id: str, request: Request):
    """Update enrollment progress (0-100%)."""
    await require_auth(request)
    db = get_db()
    body = await request.json()
    pct = int(body.get("progress_pct") or 0)
    upd = {"progress_pct": pct, "updated_at": _now()}
    if pct >= 100:
        upd["completed_at"] = _now()
    await db.dewi_lms_enrollments.update_one({"enrollment_id": enrollment_id}, {"$set": upd})
    return {"ok": True}


@router.get("/enrollments/{enrollment_id}/certificate")
async def certificate_pdf(enrollment_id: str, request: Request):
    """Generate certificate PDF for completed enrollment."""
    await require_auth(request)
    db = get_db()
    enroll = await db.dewi_lms_enrollments.find_one({"enrollment_id": enrollment_id}, {"_id": 0})
    if not enroll:
        raise HTTPException(404, "Enrollment tidak ditemukan.")
    if not enroll.get("certificate_issued"):
        raise HTTPException(400, "Sertifikat belum diterbitkan (kursus belum selesai / quiz belum lulus).")

    course = await db.dewi_lms_courses.find_one({"course_id": enroll.get("course_id")}, {"_id": 0})
    course_name = (course or {}).get("title", "Training")
    student = enroll.get("employee_name", "Peserta")

    try:
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.lib import colors
        from reportlab.lib.units import mm
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.lib.enums import TA_CENTER
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
    except ImportError:
        raise HTTPException(500, "reportlab belum terinstall.")

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4),
        leftMargin=25 * mm, rightMargin=25 * mm,
        topMargin=25 * mm, bottomMargin=25 * mm)

    GOLD = colors.HexColor("#c89b3c")
    NAVY = colors.HexColor("#1a2a4a")

    def _ornament(canvas, doc):
        canvas.saveState()
        canvas.setStrokeColor(GOLD)
        canvas.setLineWidth(3)
        canvas.rect(15 * mm, 15 * mm, doc.pagesize[0] - 30 * mm, doc.pagesize[1] - 30 * mm)
        canvas.setStrokeColor(NAVY)
        canvas.setLineWidth(1)
        canvas.rect(20 * mm, 20 * mm, doc.pagesize[0] - 40 * mm, doc.pagesize[1] - 40 * mm)
        canvas.setFont("Helvetica-Bold", 9)
        canvas.setFillColor(GOLD)
        canvas.drawCentredString(doc.pagesize[0] / 2, 25 * mm, "CV. DEWI ADITYA / PT RAHAZA — Learning Management System")
        canvas.restoreState()

    story = [
        Spacer(1, 40 * mm),
        Paragraph("SERTIFIKAT", ParagraphStyle("h", fontSize=42, fontName="Helvetica-Bold", textColor=NAVY, alignment=TA_CENTER, leading=48)),
        Paragraph("PENYELESAIAN PELATIHAN", ParagraphStyle("sub", fontSize=14, fontName="Helvetica", textColor=GOLD, alignment=TA_CENTER, leading=18, spaceBefore=6)),
        Spacer(1, 15 * mm),
        Paragraph("Diberikan kepada", ParagraphStyle("b", fontSize=12, alignment=TA_CENTER)),
        Spacer(1, 4 * mm),
        Paragraph(f"<b>{student}</b>", ParagraphStyle("n", fontSize=28, fontName="Helvetica-Bold", textColor=NAVY, alignment=TA_CENTER, leading=34)),
        Spacer(1, 8 * mm),
        Paragraph("Atas partisipasi dan keberhasilan menyelesaikan kursus", ParagraphStyle("b2", fontSize=11, alignment=TA_CENTER)),
        Spacer(1, 3 * mm),
        Paragraph(f"<b>{course_name}</b>", ParagraphStyle("c", fontSize=18, fontName="Helvetica-Bold", textColor=GOLD, alignment=TA_CENTER, leading=22)),
        Spacer(1, 15 * mm),
        Paragraph(f"Diterbitkan pada {(enroll.get('completed_at') or '')[:10]}",
                  ParagraphStyle("d", fontSize=10, alignment=TA_CENTER, textColor=colors.grey)),
        Spacer(1, 3 * mm),
        Paragraph(f"Skor Quiz: <b>{enroll.get('last_quiz_score', 100)}%</b> · ID Sertifikat: {enroll.get('certificate_id', '')[:12].upper()}",
                  ParagraphStyle("i", fontSize=9, alignment=TA_CENTER, textColor=colors.grey)),
    ]
    doc.build(story, onFirstPage=_ornament, onLaterPages=_ornament)
    buf.seek(0)
    return StreamingResponse(buf, media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="certificate_{enrollment_id[:8]}.pdf"'})
