"""Phase 6.4 — ATS / Rekrutmen (Applicant Tracking System)
Modul: Lowongan, Kandidat, Pipeline, Interview, Offer
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from motor.motor_asyncio import AsyncIOMotorDatabase
from database import get_db
from auth import require_auth
from datetime import datetime, timezone, timedelta
from typing import Optional
import uuid
import re

router = APIRouter(prefix="/api/dewi/recruitment", tags=["Recruitment"])

def now_utc():
    return datetime.now(timezone.utc)

def sid():
    return str(uuid.uuid4())

def serialize(doc):
    if doc is None:
        return None
    doc = dict(doc)
    doc.pop('_id', None)
    for k, v in doc.items():
        if isinstance(v, datetime):
            doc[k] = v.isoformat()
    return doc

PIPELINE_STAGES = [
    "Lamaran Masuk",
    "Screening CV",
    "Interview HR",
    "Interview User",
    "Offering",
    "Hired",
    "Rejected",
]

# ──────────────────────────────────────────────────────────────────────────────
# JOB POSTINGS
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/jobs")
async def list_jobs(
    db: AsyncIOMotorDatabase = Depends(get_db),
    user=Depends(require_auth),
    status: Optional[str] = None,
    dept: Optional[str] = None,
    q: Optional[str] = None,
    page: int = Query(1, ge=1), limit: int = Query(20, ge=1, le=500),
):
    filt = {}
    if status:
        filt["status"] = status
    if dept:
        filt["department"] = dept
    if q:
        filt["$or"] = [{"title": {"$regex": re.escape(q), "$options": "i"}},
                         {"department": {"$regex": re.escape(q), "$options": "i"}}]
    total = await db.dewi_recruitment_jobs.count_documents(filt)
    docs = await db.dewi_recruitment_jobs.find(filt).sort("created_at", -1).skip((page-1)*limit).limit(limit).to_list(limit)
    
    result = []
    for d in docs:
        s = serialize(d)
        # count candidates
        s["candidate_count"] = await db.dewi_recruitment_candidates.count_documents({"job_id": s["job_id"]})
        result.append(s)
    
    return {"ok": True, "total": total, "page": page, "limit": limit, "jobs": result}

@router.post("/jobs")
async def create_job(
    body: dict,
    db: AsyncIOMotorDatabase = Depends(get_db),
    user=Depends(require_auth),
):
    doc = {
        "job_id": sid(),
        "title": body.get("title", "Posisi Baru"),
        "department": body.get("department", ""),
        "location": body.get("location", "Bandung"),
        "type": body.get("type", "Full-time"),  # Full-time/Part-time/Contract/Magang
        "level": body.get("level", "Staff"),
        "salary_min": body.get("salary_min", 0),
        "salary_max": body.get("salary_max", 0),
        "headcount": body.get("headcount", 1),
        "description": body.get("description", ""),
        "requirements": body.get("requirements", []),
        "benefits": body.get("benefits", []),
        "deadline": body.get("deadline", (now_utc() + timedelta(days=30)).isoformat()),
        "status": body.get("status", "open"),  # open/closed/draft/on_hold
        "source": body.get("source", []),  # LinkedIn, Jobstreet, Internal, Referral
        "pic": body.get("pic", user.get("name", "")),
        "candidate_count": 0,
        "hired_count": 0,
        "created_by": user.get("name", ""),
        "created_at": now_utc(),
        "updated_at": now_utc(),
    }
    await db.dewi_recruitment_jobs.insert_one(doc)
    return {"ok": True, "job": serialize(doc)}

@router.get("/jobs/{job_id}")
async def get_job(
    job_id: str,
    db: AsyncIOMotorDatabase = Depends(get_db),
    user=Depends(require_auth),
):
    doc = await db.dewi_recruitment_jobs.find_one({"job_id": job_id})
    if not doc:
        raise HTTPException(404, "Lowongan tidak ditemukan")
    s = serialize(doc)
    s["candidate_count"] = await db.dewi_recruitment_candidates.count_documents({"job_id": job_id})
    return {"ok": True, "job": s}

@router.put("/jobs/{job_id}")
async def update_job(
    job_id: str, body: dict,
    db: AsyncIOMotorDatabase = Depends(get_db),
    user=Depends(require_auth),
):
    allowed = ["title","department","location","type","level","salary_min","salary_max",
               "headcount","description","requirements","benefits","deadline","status","source","pic"]
    upd = {k: body[k] for k in allowed if k in body}
    upd["updated_at"] = now_utc()
    await db.dewi_recruitment_jobs.update_one({"job_id": job_id}, {"$set": upd})
    doc = await db.dewi_recruitment_jobs.find_one({"job_id": job_id})
    return {"ok": True, "job": serialize(doc)}

@router.delete("/jobs/{job_id}")
async def delete_job(
    job_id: str,
    db: AsyncIOMotorDatabase = Depends(get_db),
    user=Depends(require_auth),
):
    await db.dewi_recruitment_jobs.delete_one({"job_id": job_id})
    await db.dewi_recruitment_candidates.delete_many({"job_id": job_id})
    return {"ok": True}

# ──────────────────────────────────────────────────────────────────────────────
# CANDIDATES
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/candidates")
async def list_candidates(
    db: AsyncIOMotorDatabase = Depends(get_db),
    user=Depends(require_auth),
    job_id: Optional[str] = None,
    stage: Optional[str] = None,
    q: Optional[str] = None,
    page: int = Query(1, ge=1), limit: int = Query(30, ge=1, le=500),
):
    filt = {}
    if job_id:
        filt["job_id"] = job_id
    if stage:
        filt["stage"] = stage
    if q:
        filt["$or"] = [{"name": {"$regex": re.escape(q), "$options": "i"}},
                         {"email": {"$regex": re.escape(q), "$options": "i"}}]
    total = await db.dewi_recruitment_candidates.count_documents(filt)
    docs = await db.dewi_recruitment_candidates.find(filt).sort("applied_at", -1).skip((page-1)*limit).limit(limit).to_list(limit)
    return {"ok": True, "total": total, "candidates": [serialize(d) for d in docs]}

@router.post("/candidates")
async def add_candidate(
    body: dict,
    db: AsyncIOMotorDatabase = Depends(get_db),
    user=Depends(require_auth),
):
    job_id = body.get("job_id", "")
    if job_id:
        job = await db.dewi_recruitment_jobs.find_one({"job_id": job_id})
        if not job:
            raise HTTPException(404, "Lowongan tidak ditemukan")
    
    doc = {
        "candidate_id": sid(),
        "job_id": job_id,
        "job_title": body.get("job_title", ""),
        "name": body.get("name", ""),
        "email": body.get("email", ""),
        "phone": body.get("phone", ""),
        "gender": body.get("gender", ""),
        "birth_date": body.get("birth_date", ""),
        "address": body.get("address", ""),
        "education": body.get("education", ""),
        "experience_years": body.get("experience_years", 0),
        "skills": body.get("skills", []),
        "cv_url": body.get("cv_url", ""),
        "portfolio_url": body.get("portfolio_url", ""),
        "source": body.get("source", "Walk-in"),  # LinkedIn/Jobstreet/Referral/Walk-in
        "stage": body.get("stage", "Lamaran Masuk"),
        "rating": body.get("rating", 0),  # 1-5
        "notes": body.get("notes", ""),
        # ─── P2 Referral program ───────────────────────────────────────────
        "referral_employee_id": body.get("referral_employee_id") or None,
        "referral_employee_name": body.get("referral_employee_name") or "",
        "referral_bonus": float(body.get("referral_bonus") or 0),
        "referral_bonus_paid": False,
        "timeline": [
            {"stage": "Lamaran Masuk", "date": now_utc().isoformat(), "by": user.get("name", "System"), "note": ""}
        ],
        "interviews": [],
        "offer": None,
        "applied_at": now_utc(),
        "updated_at": now_utc(),
        "created_by": user.get("name", ""),
    }
    await db.dewi_recruitment_candidates.insert_one(doc)
    if job_id:
        await db.dewi_recruitment_jobs.update_one({"job_id": job_id}, {"$inc": {"candidate_count": 1}})
    return {"ok": True, "candidate": serialize(doc)}

@router.get("/candidates/{candidate_id}")
async def get_candidate(
    candidate_id: str,
    db: AsyncIOMotorDatabase = Depends(get_db),
    user=Depends(require_auth),
):
    doc = await db.dewi_recruitment_candidates.find_one({"candidate_id": candidate_id})
    if not doc:
        raise HTTPException(404, "Kandidat tidak ditemukan")
    return {"ok": True, "candidate": serialize(doc)}

@router.put("/candidates/{candidate_id}")
async def update_candidate(
    candidate_id: str, body: dict,
    db: AsyncIOMotorDatabase = Depends(get_db),
    user=Depends(require_auth),
):
    candidate = await db.dewi_recruitment_candidates.find_one({"candidate_id": candidate_id})
    if not candidate:
        raise HTTPException(404)
    
    allowed = ["name", "email", "phone", "birth_date", "address", "education",
               "experience_years", "skills", "cv_url", "portfolio_url", "source",
               "rating", "notes", "offer",
               "referral_employee_id", "referral_employee_name", "referral_bonus", "referral_bonus_paid"]
    upd = {k: body[k] for k in allowed if k in body}
    
    # handle stage change
    if "stage" in body and body["stage"] != candidate.get("stage"):
        new_stage = body["stage"]
        upd["stage"] = new_stage
        timeline = candidate.get("timeline", [])
        timeline.append({
            "stage": new_stage,
            "date": now_utc().isoformat(),
            "by": user.get("name", "System"),
            "note": body.get("stage_note", "")
        })
        upd["timeline"] = timeline
        
        # if hired, increment job hired count + auto-create employee + onboarding
        if new_stage == "Hired" and candidate.get("job_id"):
            await db.dewi_recruitment_jobs.update_one(
                {"job_id": candidate["job_id"]}, {"$inc": {"hired_count": 1}}
            )

            # ─── P1.2 Auto-trigger: create employee record + onboarding ───────
            try:
                if not candidate.get("employee_id"):
                    import uuid as _uuid
                    from datetime import datetime as _dt, timezone as _tz
                    # Build employee_code from candidate name
                    nm = (candidate.get("name") or "HIRE").upper().split()
                    initials = "".join(w[0] for w in nm[:2]) if nm else "NEW"
                    code_prefix = f"EMP-{initials}-{_dt.now().strftime('%y%m')}"
                    # Unique suffix
                    seq = 1
                    while await db.rahaza_employees.find_one({"employee_code": f"{code_prefix}-{seq:03d}"}):
                        seq += 1
                    emp_code = f"{code_prefix}-{seq:03d}"

                    job = await db.dewi_recruitment_jobs.find_one({"job_id": candidate["job_id"]}, {"_id": 0})
                    job_title = (job or {}).get("title") or "Staff"
                    department = (job or {}).get("department") or ""

                    new_emp = {
                        "id": str(_uuid.uuid4()),
                        "employee_code": emp_code,
                        "name": candidate.get("name", ""),
                        "department": department,
                        "job_title": job_title,
                        "location_id": None,
                        "phone": candidate.get("phone", ""),
                        "email": candidate.get("email", ""),
                        "contract_type": (candidate.get("offer") or {}).get("contract_type") or "PKWT",
                        "contract_start_date": (candidate.get("offer") or {}).get("start_date"),
                        "contract_end_date": (candidate.get("offer") or {}).get("end_date"),
                        "wage_scheme": "bulanan",
                        "base_rate": (candidate.get("offer") or {}).get("salary") or 0,
                        "joined_at": _dt.now(_tz.utc).isoformat(),
                        "gender": "", "birth_date": None, "birth_place": "",
                        "marital_status": "", "religion": "", "nationality": "Indonesia",
                        "ktp_address": "", "current_address": "",
                        "education_level": "", "education_institution": "", "education_major": "",
                        "photo_url": "",
                        "ktp_number": "", "npwp_number": "", "tax_ptkp": "TK/0",
                        "bpjs_kesehatan_number": "", "bpjs_ketenagakerjaan_number": "",
                        "bank_name": "", "bank_account_number": "", "bank_account_holder": candidate.get("name", ""),
                        "emergency_contact_name": "", "emergency_phone": "", "emergency_relation": "",
                        "active": True,
                        "from_candidate_id": candidate_id,
                        "created_at": _dt.now(_tz.utc),
                        "updated_at": _dt.now(_tz.utc),
                    }
                    await db.rahaza_employees.insert_one(new_emp)
                    upd["employee_id"] = new_emp["id"]

                    # Create onboarding checklist from default template
                    tpl = await db.dewi_onboarding_templates.find_one(
                        {"is_default": True}, {"_id": 0}
                    )
                    if not tpl:
                        tpl = await db.dewi_onboarding_templates.find_one({}, {"_id": 0})

                    # Fallback: create empty checklist with minimal tasks if no template
                    if not tpl:
                        import logging
                        logging.getLogger(__name__).info("Auto-onboarding: no template found, creating empty checklist")
                        tpl = {
                            "template_id": None,
                            "name": "Default (no template — tolong buat template)",
                            "tasks": [
                                {"title": "Verifikasi dokumen karyawan", "category": "Documents", "due_day": 1},
                                {"title": "Setup akun email & sistem", "category": "IT", "due_day": 1},
                                {"title": "Orientasi perusahaan", "category": "Orientation", "due_day": 3},
                                {"title": "Tanda tangan kontrak kerja", "category": "Legal", "due_day": 7},
                            ],
                        }

                    tasks = [
                        {
                            "task_id": str(_uuid.uuid4()),
                            "title": t.get("title", ""),
                            "description": t.get("description", ""),
                            "category": t.get("category", "General"),
                            "due_day": t.get("due_day", 7),
                            "status": "pending",
                            "completed_at": None,
                            "completed_by": None,
                        }
                        for t in (tpl.get("tasks") or [])
                    ]
                    checklist = {
                        "checklist_id": str(_uuid.uuid4()),
                        "employee_id": new_emp["id"],
                        "employee_name": new_emp["name"],
                        "employee_code": new_emp["employee_code"],
                        "template_id": tpl.get("template_id"),
                        "template_name": tpl.get("name", ""),
                        "from_candidate_id": candidate_id,
                        "status": "in_progress",
                        "started_at": _dt.now(_tz.utc).isoformat(),
                        "completed_at": None,
                        "tasks": tasks,
                        "created_at": _dt.now(_tz.utc),
                        "updated_at": _dt.now(_tz.utc),
                    }
                    await db.dewi_onboarding_checklists.insert_one(checklist)
                    upd["onboarding_checklist_id"] = checklist["checklist_id"]
            except Exception as e:
                import logging
                logging.getLogger(__name__).error(f"Auto-onboarding failed: {e}")

        # ─── Mock Email Notification ─────────────────────────────────────────
        _STAGE_EMAIL = {
            "Screening CV": {
                "subject": "CV Anda Sedang Dalam Proses Seleksi — {job_title}",
                "body": (
                    "Yth. {name},\n\n"
                    "Terima kasih telah melamar posisi {job_title} di CV. Dewi Aditya. "
                    "CV Anda saat ini sedang dalam tahap seleksi oleh tim HR kami. "
                    "Kami akan menghubungi Anda kembali jika ada perkembangan lebih lanjut.\n\n"
                    "Salam,\nTim HR CV. Dewi Aditya"
                ),
            },
            "Interview HR": {
                "subject": "Undangan Interview HR — {job_title}",
                "body": (
                    "Yth. {name},\n\n"
                    "Selamat! Anda terpilih untuk mengikuti tahap Interview HR untuk posisi {job_title}. "
                    "Tim HR kami akan menghubungi Anda segera untuk mengkonfirmasi jadwal, lokasi, dan detail wawancara.\n\n"
                    "Mohon mempersiapkan dokumen pendukung (CV, portofolio, dll.).\n\n"
                    "Salam,\nTim HR CV. Dewi Aditya"
                ),
            },
            "Interview User": {
                "subject": "Undangan Interview User — {job_title}",
                "body": (
                    "Yth. {name},\n\n"
                    "Selamat, Anda berhasil lolos ke tahap Interview User untuk posisi {job_title}! "
                    "Tim manajerial terkait akan segera menghubungi Anda untuk penjadwalan wawancara lanjutan.\n\n"
                    "Salam,\nTim HR CV. Dewi Aditya"
                ),
            },
            "Offering": {
                "subject": "Penawaran Kerja dari CV. Dewi Aditya — {job_title}",
                "body": (
                    "Yth. {name},\n\n"
                    "Kami dengan senang hati menyampaikan bahwa Anda terpilih untuk bergabung bersama kami "
                    "dalam posisi {job_title}. Detail penawaran kerja termasuk kompensasi dan fasilitas "
                    "akan disampaikan oleh tim HR kami secara langsung.\n\n"
                    "Mohon konfirmasi kehadiran Anda paling lambat 3 hari kerja sejak email ini diterima.\n\n"
                    "Salam,\nTim HR CV. Dewi Aditya"
                ),
            },
            "Hired": {
                "subject": "Selamat Bergabung di CV. Dewi Aditya! — {job_title}",
                "body": (
                    "Yth. {name},\n\n"
                    "Selamat dan selamat datang di keluarga besar CV. Dewi Aditya! "
                    "Kami sangat senang Anda akan bergabung sebagai {job_title}.\n\n"
                    "Checklist onboarding Anda telah disiapkan. Tim HR akan menghubungi Anda "
                    "mengenai jadwal hari pertama masuk kerja.\n\n"
                    "Salam hangat,\nTim HR CV. Dewi Aditya"
                ),
            },
            "Rejected": {
                "subject": "Informasi Hasil Seleksi Lamaran — {job_title}",
                "body": (
                    "Yth. {name},\n\n"
                    "Terima kasih atas minat Anda untuk bergabung di CV. Dewi Aditya dan waktu yang "
                    "telah Anda luangkan dalam proses seleksi posisi {job_title}.\n\n"
                    "Setelah melalui pertimbangan yang matang, kami belum dapat melanjutkan proses "
                    "rekrutmen Anda pada kesempatan ini. Hal ini bukan berarti penilaian negatif "
                    "terhadap kompetensi Anda.\n\n"
                    "Kami menyimpan data Anda dan akan menghubungi jika ada kesempatan yang sesuai.\n\n"
                    "Salam,\nTim HR CV. Dewi Aditya"
                ),
            },
        }
        if new_stage in _STAGE_EMAIL and candidate.get("email"):
            tpl = _STAGE_EMAIL[new_stage]
            email_entry = {
                "log_id": sid(),
                "to": candidate.get("email", ""),
                "subject": tpl["subject"].format(
                    name=candidate.get("name", ""),
                    job_title=candidate.get("job_title", "")
                ),
                "body": tpl["body"].format(
                    name=candidate.get("name", ""),
                    job_title=candidate.get("job_title", "")
                ),
                "stage": new_stage,
                "sent_at": now_utc().isoformat(),
                "sent_by": user.get("name", "System"),
                "status": "mock_sent",
            }
            email_logs = candidate.get("email_logs", [])
            email_logs.append(email_entry)
            upd["email_logs"] = email_logs

    upd["updated_at"] = now_utc()
    await db.dewi_recruitment_candidates.update_one({"candidate_id": candidate_id}, {"$set": upd})
    doc = await db.dewi_recruitment_candidates.find_one({"candidate_id": candidate_id})
    return {"ok": True, "candidate": serialize(doc)}

@router.post("/candidates/{candidate_id}/interviews")
async def add_interview(
    candidate_id: str, body: dict,
    db: AsyncIOMotorDatabase = Depends(get_db),
    user=Depends(require_auth),
):
    candidate = await db.dewi_recruitment_candidates.find_one({"candidate_id": candidate_id})
    if not candidate:
        raise HTTPException(404)
    
    interview = {
        "interview_id": sid(),
        "type": body.get("type", "HR Interview"),
        "scheduled_at": body.get("scheduled_at", ""),
        "interviewer": body.get("interviewer", ""),
        "mode": body.get("mode", "Tatap Muka"),  # Tatap Muka/Video Call/Phone
        "status": "scheduled",  # scheduled/done/cancelled/no_show
        "result": None,  # pass/fail/hold
        "score": None,
        "notes": body.get("notes", ""),
        "created_at": now_utc().isoformat(),
    }
    
    interviews = candidate.get("interviews", [])
    interviews.append(interview)
    
    await db.dewi_recruitment_candidates.update_one(
        {"candidate_id": candidate_id},
        {"$set": {"interviews": interviews, "updated_at": now_utc()}}
    )
    return {"ok": True, "interview": interview}

@router.put("/candidates/{candidate_id}/interviews/{interview_id}")
async def update_interview(
    candidate_id: str, interview_id: str, body: dict,
    db: AsyncIOMotorDatabase = Depends(get_db),
    user=Depends(require_auth),
):
    candidate = await db.dewi_recruitment_candidates.find_one({"candidate_id": candidate_id})
    if not candidate:
        raise HTTPException(404)
    
    interviews = candidate.get("interviews", [])
    for iv in interviews:
        if iv["interview_id"] == interview_id:
            iv.update({k: body[k] for k in ["status","result","score","notes"] if k in body})
            break
    
    await db.dewi_recruitment_candidates.update_one(
        {"candidate_id": candidate_id},
        {"$set": {"interviews": interviews, "updated_at": now_utc()}}
    )
    return {"ok": True}

@router.delete("/candidates/{candidate_id}")
async def delete_candidate(
    candidate_id: str,
    db: AsyncIOMotorDatabase = Depends(get_db),
    user=Depends(require_auth),
):
    await db.dewi_recruitment_candidates.delete_one({"candidate_id": candidate_id})
    return {"ok": True}


@router.post("/candidates/{candidate_id}/upload-cv")
async def upload_candidate_cv(
    candidate_id: str, body: dict,
    db: AsyncIOMotorDatabase = Depends(get_db),
    user=Depends(require_auth),
):
    """Upload or link CV for a candidate (accepts cv_url string or cv_data base64 + cv_filename)."""
    candidate = await db.dewi_recruitment_candidates.find_one({"candidate_id": candidate_id})
    if not candidate:
        raise HTTPException(404, "Kandidat tidak ditemukan")

    upd: dict = {"updated_at": now_utc()}
    if body.get("cv_url"):
        upd["cv_url"] = body["cv_url"]
    if body.get("cv_data"):
        upd["cv_data"] = body["cv_data"]        # base64 encoded string
        upd["cv_filename"] = body.get("cv_filename", "cv.pdf")
        upd["cv_size"] = body.get("cv_size", 0)

    await db.dewi_recruitment_candidates.update_one({"candidate_id": candidate_id}, {"$set": upd})
    return {"ok": True, "message": "CV berhasil diupload"}


@router.post("/candidates/{candidate_id}/notes")
async def add_candidate_note(
    candidate_id: str, body: dict,
    db: AsyncIOMotorDatabase = Depends(get_db),
    user=Depends(require_auth),
):
    candidate = await db.dewi_recruitment_candidates.find_one({"candidate_id": candidate_id})
    if not candidate:
        raise HTTPException(404, "Kandidat tidak ditemukan")

    note = {
        "note_id": sid(),
        "text": body.get("text", ""),
        "by": user.get("name", ""),
        "created_at": now_utc().isoformat(),
    }
    notes = candidate.get("activity_notes", [])
    notes.append(note)
    await db.dewi_recruitment_candidates.update_one(
        {"candidate_id": candidate_id},
        {"$set": {"activity_notes": notes, "updated_at": now_utc()}}
    )
    return {"ok": True, "note": note}

# ──────────────────────────────────────────────────────────────────────────────
# PIPELINE VIEW
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/pipeline")
async def get_pipeline(
    db: AsyncIOMotorDatabase = Depends(get_db),
    user=Depends(require_auth),
    job_id: Optional[str] = None,
):
    filt = {}
    if job_id:
        filt["job_id"] = job_id
    
    all_candidates = await db.dewi_recruitment_candidates.find(filt).to_list(500)
    
    result = {}
    for stage in PIPELINE_STAGES:
        result[stage] = {
            "count": 0,
            "candidates": []
        }
    
    for c in all_candidates:
        stage = c.get("stage", "Lamaran Masuk")
        if stage not in result:
            result[stage] = {"count": 0, "candidates": []}
        sc = serialize(c)
        result[stage]["candidates"].append(sc)
        result[stage]["count"] += 1
    
    return {"ok": True, "stages": PIPELINE_STAGES, "pipeline": result}

# ──────────────────────────────────────────────────────────────────────────────
# ANALYTICS
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/analytics")
async def recruitment_analytics(
    db: AsyncIOMotorDatabase = Depends(get_db),
    user=Depends(require_auth),
):
    total_jobs = await db.dewi_recruitment_jobs.count_documents({})
    open_jobs = await db.dewi_recruitment_jobs.count_documents({"status": "open"})
    total_candidates = await db.dewi_recruitment_candidates.count_documents({})
    hired = await db.dewi_recruitment_candidates.count_documents({"stage": "Hired"})
    rejected = await db.dewi_recruitment_candidates.count_documents({"stage": "Rejected"})
    in_progress = total_candidates - hired - rejected
    
    # pipeline breakdown
    pipeline = [
        {"$group": {"_id": "$stage", "count": {"$sum": 1}}}
    ]
    stage_counts = await db.dewi_recruitment_candidates.aggregate(pipeline).to_list(20)
    stage_map = {d["_id"]: d["count"] for d in stage_counts}
    
    # source breakdown
    src_pipeline = [
        {"$group": {"_id": "$source", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}}
    ]
    source_breakdown = await db.dewi_recruitment_candidates.aggregate(src_pipeline).to_list(10)
    
    # top jobs
    top_jobs = await db.dewi_recruitment_jobs.find({"status": "open"}).sort("candidate_count", -1).limit(5).to_list(5)
    
    return {
        "ok": True,
        "summary": {
            "total_jobs": total_jobs,
            "open_jobs": open_jobs,
            "total_candidates": total_candidates,
            "hired": hired,
            "rejected": rejected,
            "in_progress": in_progress,
            "conversion_rate": round(hired / total_candidates * 100, 1) if total_candidates else 0,
        },
        "pipeline_stages": [{"stage": s, "count": stage_map.get(s, 0)} for s in PIPELINE_STAGES],
        "source_breakdown": [{"source": d["_id"], "count": d["count"]} for d in source_breakdown],
        "top_open_jobs": [serialize(j) for j in top_jobs],
    }

# ──────────────────────────────────────────────────────────────────────────────
# SEED
# ──────────────────────────────────────────────────────────────────────────────

@router.post("/seed")
async def seed_recruitment(
    db: AsyncIOMotorDatabase = Depends(get_db),
    user=Depends(require_auth),
):
    await db.dewi_recruitment_jobs.delete_many({})
    await db.dewi_recruitment_candidates.delete_many({})
    
    jobs = [
        {"job_id": "job-001", "title": "Operator Jahit Senior", "department": "Produksi", "location": "Bandung",
         "type": "Full-time", "level": "Senior", "salary_min": 3500000, "salary_max": 5000000,
         "headcount": 5, "description": "Dibutuhkan operator jahit berpengalaman untuk lini produksi garmen.",
         "requirements": ["Min. 2 tahun pengalaman jahit", "Terbiasa dengan target produksi", "Disiplin dan teliti"],
         "benefits": ["BPJS Kesehatan & Ketenagakerjaan", "Transport allowance", "Makan siang"],
         "deadline": (now_utc() + timedelta(days=14)).isoformat(), "status": "open",
         "source": ["Jobstreet", "Walk-in"], "pic": "HR Manager",
         "candidate_count": 12, "hired_count": 2,
         "created_by": "Admin", "created_at": now_utc(), "updated_at": now_utc()},
        {"job_id": "job-002", "title": "QC Inspector", "department": "Quality Control", "location": "Bandung",
         "type": "Full-time", "level": "Staff", "salary_min": 3000000, "salary_max": 4500000,
         "headcount": 2, "description": "Posisi QC Inspector untuk menjaga standar kualitas produk.",
         "requirements": ["Pendidikan minimal D3", "Teliti dan detail-oriented", "Pengalaman QC garmen diutamakan"],
         "benefits": ["BPJS Kesehatan & Ketenagakerjaan", "Bonus kinerja"],
         "deadline": (now_utc() + timedelta(days=21)).isoformat(), "status": "open",
         "source": ["LinkedIn", "Referral"], "pic": "QC Manager",
         "candidate_count": 6, "hired_count": 0,
         "created_by": "Admin", "created_at": now_utc(), "updated_at": now_utc()},
        {"job_id": "job-003", "title": "Staff Admin & Keuangan", "department": "Keuangan", "location": "Bandung",
         "type": "Full-time", "level": "Staff", "salary_min": 2800000, "salary_max": 3800000,
         "headcount": 1, "description": "Staf administrasi dan keuangan untuk mendukung operasional kantor.",
         "requirements": ["S1 Akuntansi/Manajemen", "Menguasai Excel & software akuntansi", "Fresh graduate welcome"],
         "benefits": ["BPJS Kesehatan & Ketenagakerjaan", "THR"],
         "deadline": (now_utc() - timedelta(days=5)).isoformat(), "status": "closed",
         "source": ["Jobstreet"], "pic": "Finance Manager",
         "candidate_count": 20, "hired_count": 1,
         "created_by": "Admin", "created_at": now_utc(), "updated_at": now_utc()},
        {"job_id": "job-004", "title": "Supervisor Produksi", "department": "Produksi", "location": "Bandung",
         "type": "Full-time", "level": "Supervisor", "salary_min": 5000000, "salary_max": 7000000,
         "headcount": 1, "description": "Supervisor yang akan memimpin dan mengkoordinir lini produksi.",
         "requirements": ["Min. 3 tahun pengalaman di industri garmen", "Kemampuan leadership yang baik", "Familiar dengan sistem Lean Production"],
         "benefits": ["BPJS", "Tunjangan jabatan", "Bonus kinerja kuartalan"],
         "deadline": (now_utc() + timedelta(days=30)).isoformat(), "status": "open",
         "source": ["LinkedIn", "Referral"], "pic": "GM Operasional",
         "candidate_count": 4, "hired_count": 0,
         "created_by": "Admin", "created_at": now_utc(), "updated_at": now_utc()},
    ]
    for j in jobs:
        await db.dewi_recruitment_jobs.insert_one(j)
    
    # Sample candidates
    candidate_names = [
        ("Budi Santoso", "budi.s@email.com", "08123456789", "job-001", "Screening CV", "Jobstreet", 3),
        ("Sari Dewi", "sari.d@email.com", "08234567890", "job-001", "Interview HR", "Walk-in", 4),
        ("Ahmad Fauzi", "ahmad.f@email.com", "08345678901", "job-001", "Hired", "Referral", 5),
        ("Rini Pratiwi", "rini.p@email.com", "08456789012", "job-001", "Lamaran Masuk", "Jobstreet", 2),
        ("Dedi Kurniawan", "dedi.k@email.com", "08567890123", "job-002", "Interview HR", "LinkedIn", 4),
        ("Yuni Lestari", "yuni.l@email.com", "08678901234", "job-002", "Interview User", "Referral", 4),
        ("Agus Priyanto", "agus.p@email.com", "08789012345", "job-002", "Screening CV", "LinkedIn", 3),
        ("Maya Sari", "maya.s@email.com", "08890123456", "job-004", "Interview HR", "LinkedIn", 4),
        ("Eko Wahyudi", "eko.w@email.com", "08901234567", "job-004", "Offering", "Referral", 5),
        ("Fitri Handayani", "fitri.h@email.com", "08012345678", "job-001", "Rejected", "Walk-in", 2),
    ]
    
    for cn in candidate_names:
        name, email, phone, job_id, stage, source, rating = cn
        job = next((j for j in jobs if j["job_id"] == job_id), None)
        timeline = [{"stage": "Lamaran Masuk", "date": (now_utc() - timedelta(days=10)).isoformat(), "by": "System", "note": ""}]
        if stage != "Lamaran Masuk":
            idx = PIPELINE_STAGES.index(stage) if stage in PIPELINE_STAGES else 0
            for i in range(1, idx + 1):
                timeline.append({"stage": PIPELINE_STAGES[i], "date": (now_utc() - timedelta(days=10-i)).isoformat(), "by": "HR", "note": ""})
        
        doc = {
            "candidate_id": sid(),
            "job_id": job_id,
            "job_title": job["title"] if job else "",
            "name": name, "email": email, "phone": phone,
            "gender": "L" if name.split()[0] in ["Budi","Ahmad","Dedi","Agus","Eko"] else "P",
            "education": ["SMA/SMK","D3","S1"][rating % 3],
            "experience_years": rating,
            "skills": ["Jahit", "QC", "Ms Office"][:rating-1],
            "cv_url": "", "portfolio_url": "",
            "source": source, "stage": stage, "rating": rating,
            "notes": "", "timeline": timeline,
            "interviews": [], "offer": None,
            "applied_at": now_utc() - timedelta(days=10),
            "updated_at": now_utc(),
            "created_by": "Admin",
        }
        await db.dewi_recruitment_candidates.insert_one(doc)
    
    return {"ok": True, "message": "Recruitment seed selesai", "jobs": len(jobs), "candidates": len(candidate_names)}


# ──────────────────────────────────────────────────────────────────────────────
# TALENT POOL
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/talent-pool")
async def list_talent_pool(
    db: AsyncIOMotorDatabase = Depends(get_db),
    user=Depends(require_auth),
    search: Optional[str] = None,
):
    """Daftar kandidat yang ada di Talent Pool."""
    filt: dict = {"is_talent_pool": True}
    if search:
        filt["$or"] = [
            {"name": {"$regex": search, "$options": "i"}},
            {"position_applied": {"$regex": search, "$options": "i"}},
            {"skills": {"$regex": search, "$options": "i"}},
        ]
    docs = await db.dewi_recruitment_candidates.find(filt, {"_id": 0}).sort("talent_pool_added_at", -1).to_list(500)
    return {"ok": True, "candidates": [serialize(d) for d in docs], "total": len(docs)}


@router.post("/talent-pool/{candidate_id}/toggle")
async def toggle_talent_pool(
    candidate_id: str,
    db: AsyncIOMotorDatabase = Depends(get_db),
    user=Depends(require_auth),
):
    """Masukkan atau keluarkan kandidat dari Talent Pool."""
    cand = await db.dewi_recruitment_candidates.find_one({"candidate_id": candidate_id}, {"_id": 0})
    if not cand:
        raise HTTPException(404, "Kandidat tidak ditemukan.")

    is_now_in_pool = not cand.get("is_talent_pool", False)
    upd = {
        "is_talent_pool": is_now_in_pool,
        "updated_at": now_utc(),
    }
    if is_now_in_pool:
        upd["talent_pool_added_at"] = now_utc()
        upd["talent_pool_added_by"] = user.get("name", "")
    else:
        upd["talent_pool_removed_at"] = now_utc()

    await db.dewi_recruitment_candidates.update_one({"candidate_id": candidate_id}, {"$set": upd})
    action = "Ditambahkan ke" if is_now_in_pool else "Dikeluarkan dari"
    return {"ok": True, "is_talent_pool": is_now_in_pool, "message": f"{action} Talent Pool: {cand.get('name')}"}


@router.put("/talent-pool/{candidate_id}/notes")
async def update_talent_pool_notes(
    candidate_id: str,
    db: AsyncIOMotorDatabase = Depends(get_db),
    user=Depends(require_auth),
):
    """Update skills & catatan kandidat di Talent Pool."""
    raise HTTPException(400, "Gunakan PUT /candidates/{id} untuk update data kandidat.")


@router.get("/talent-pool/stats")
async def talent_pool_stats(
    db: AsyncIOMotorDatabase = Depends(get_db),
    user=Depends(require_auth),
):
    """Statistik Talent Pool."""
    total = await db.dewi_recruitment_candidates.count_documents({"is_talent_pool": True})
    by_stage = {}
    pipeline = [
        {"$match": {"is_talent_pool": True}},
        {"$group": {"_id": "$stage", "count": {"$sum": 1}}},
    ]
    async for doc in db.dewi_recruitment_candidates.aggregate(pipeline):
        by_stage[doc["_id"]] = doc["count"]

    return {"ok": True, "total": total, "by_stage": by_stage}
