"""
LMS Student API - Student-Facing Learning Management System
Portal Kolaborasi Phase 2

Endpoints for students to:
- Browse course catalog
- Enroll in courses
- View learning materials
- Submit assignments
- Track progress
- Earn certificates
"""

import logging
from fastapi import APIRouter, Depends, HTTPException, Body, Query
from motor.motor_asyncio import AsyncIOMotorDatabase
from database import get_db
from auth import require_auth
from datetime import datetime, timezone
from typing import Optional
import uuid
import re

router = APIRouter(prefix="/api/lms/student", tags=["LMS Student"])

# Import notification helper (lazy to avoid circular import)
async def _notify(db, user_id, notif_type, title, content, source_type='course', source_id='', source_url=''):
    try:
        from routes.notifications import create_notification
        await create_notification(db, user_id=user_id, notif_type=notif_type,
            title=title, content=content, source_type=source_type,
            source_id=source_id, source_url=source_url)
    except Exception:
        logging.getLogger(__name__).debug("suppressed exception", exc_info=True)


async def _auto_create_course_channel(db, course_id: str, course_title: str, user_id: str):
    """
    Phase 3.4: Auto-create a discussion channel when a student enrolls.
    Channel name: course-{slug}  (e.g. 'course-keselamatan-kerja-k3-2024')
    Adds the enrolling student as a member if channel already exists.
    """
    try:
        import re as _re
        slug = _re.sub(r'[^a-z0-9]+', '-', course_title.lower()).strip('-')[:40]
        channel_name = f"course-{slug}"

        # Check if channel exists
        existing = await db.comm_channels.find_one({'name': channel_name})
        if existing:
            # Just add student as member if not already
            if user_id not in existing.get('members', []):
                await db.comm_channels.update_one(
                    {'name': channel_name},
                    {'$addToSet': {'members': user_id}}
                )
            return existing['id']

        # Create the channel
        channel_id = str(uuid.uuid4())
        now = now_utc()
        channel_doc = {
            'id': channel_id,
            'name': channel_name,
            'description': f'Diskusi untuk course: {course_title}',
            'type': 'course',   # custom type for LMS channels
            'members': [user_id],
            'course_id': course_id,
            'created_by': user_id,
            'created_by_name': 'LMS System',
            'archived': False,
            'created_at': now,
            'updated_at': now,
            'last_message': None,
            'last_message_at': None,
            'member_count': 1,
        }
        await db.comm_channels.insert_one(channel_doc)

        # Send welcome system message
        welcome_msg = {
            'id': str(uuid.uuid4()),
            'channel_id': channel_id,
            'sender_id': 'system',
            'sender_name': 'LMS System',
            'sender_role': 'system',
            'content': f'👋 Selamat datang di channel diskusi *{course_title}*!\n\nChannel ini dibuat otomatis untuk memfasilitasi diskusi antar peserta course. Silakan bertanya, berbagi, dan berdiskusi di sini.',
            'type': 'system',
            'attachments': [],
            'reactions': {},
            'edited': False,
            'deleted': False,
            'created_at': now,
            'updated_at': now,
        }
        await db.comm_messages.insert_one(welcome_msg)
        return channel_id
    except Exception:
        logging.getLogger(__name__).debug("suppressed exception", exc_info=True)
    return None

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

# ──────────────────────────────────────────────────────────────────────────────
# COURSE CATALOG
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/catalog")
async def get_course_catalog(
    db: AsyncIOMotorDatabase = Depends(get_db),
    user=Depends(require_auth),
    category: Optional[str] = None,
    level: Optional[str] = None,
    search: Optional[str] = None,
    mandatory: Optional[bool] = None,
    sort: str = "newest",  # newest | popular | rating
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=200),
):
    """
    Browse course catalog with filters
    Returns: List of courses with enrollment status
    """
    user_id = user.get("id")
    
    # Build filter
    filt = {"status": "active"}  # Only show active courses
    if category:
        filt["category"] = category
    if level:
        filt["level"] = level
    if search:
        filt["$or"] = [
            {"title": {"$regex": re.escape(search), "$options": "i"}},
            {"description": {"$regex": re.escape(search), "$options": "i"}},
        ]
    
    # Sort
    sort_by = [("created_at", -1)]  # Default: newest
    if sort == "popular":
        sort_by = [("enrollment_count", -1)]
    elif sort == "rating":
        sort_by = [("rating", -1)]
    
    # Get courses
    total = await db.dewi_lms_courses.count_documents(filt)
    courses_cursor = db.dewi_lms_courses.find(filt).sort(sort_by).skip((page-1)*limit).limit(limit)
    courses = await courses_cursor.to_list(limit)
    
    # Check enrollment status for each course
    course_ids = [c["course_id"] for c in courses]
    enrollments = await db.dewi_lms_enrollments.find({
        "user_id": user_id,
        "course_id": {"$in": course_ids}
    }).to_list(len(course_ids))
    
    enrollment_map = {e["course_id"]: e for e in enrollments}
    
    # Build response
    result = []
    for c in courses:
        course_data = serialize(c)
        course_data["is_enrolled"] = c["course_id"] in enrollment_map
        if course_data["is_enrolled"]:
            enrollment = enrollment_map[c["course_id"]]
            course_data["enrollment_status"] = enrollment.get("status")
            course_data["progress_percent"] = enrollment.get("progress_percent", 0)
        result.append(course_data)
    
    return {
        "ok": True,
        "courses": result,
        "total": total,
        "page": page,
        "limit": limit,
    }


# ──────────────────────────────────────────────────────────────────────────────
# MY COURSES
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/my-courses")
async def get_my_courses(
    db: AsyncIOMotorDatabase = Depends(get_db),
    user=Depends(require_auth),
    status: str = "all",  # all | in_progress | completed | not_started
):
    """
    Get all courses the student is enrolled in
    """
    user_id = user.get("id")
    
    # Build filter
    filt = {"user_id": user_id}
    if status != "all":
        filt["status"] = status
    
    # Get enrollments
    enrollments = await db.dewi_lms_enrollments.find(filt).sort("enrolled_at", -1).to_list(100)
    
    # Get course details for each enrollment
    course_ids = [e["course_id"] for e in enrollments]
    courses = await db.dewi_lms_courses.find({"course_id": {"$in": course_ids}}).to_list(len(course_ids))
    course_map = {c["course_id"]: c for c in courses}
    
    # Build response
    result = []
    for e in enrollments:
        course = course_map.get(e["course_id"])
        if not course:
            continue
            
        course_data = serialize(course)
        course_data["enrollment_id"] = e["enrollment_id"]
        course_data["enrollment_status"] = e.get("status")
        course_data["progress_percent"] = e.get("progress_percent", 0)
        course_data["completed_items"] = e.get("completed_items", 0)
        course_data["total_items"] = len(course.get("materials", []))
        course_data["enrolled_at"] = serialize(e).get("enrolled_at")
        course_data["last_accessed"] = serialize(e).get("last_accessed")
        
        # Get next lesson/material to continue
        if e.get("status") == "in_progress":
            # Find first incomplete material
            progress_records = await db.dewi_lms_progress.find({
                "enrollment_id": e["enrollment_id"],
                "status": "completed"
            }).to_list(100)
            
            completed_material_ids = {p["material_id"] for p in progress_records}
            # Fetch real material objects (course.materials is just list of IDs)
            materials = await db.dewi_lms_materials.find(
                {"course_id": e["course_id"]}
            ).sort("order", 1).to_list(100)
            
            next_material = None
            for mat in materials:
                if mat.get("material_id") and mat["material_id"] not in completed_material_ids:
                    next_material = {
                        "material_id": mat["material_id"],
                        "title": mat.get("title", ""),
                        "type": mat.get("type", ""),
                    }
                    break
            
            course_data["next_material"] = next_material
            # Update total_items based on actual materials count
            course_data["total_items"] = len(materials)
        
        result.append(course_data)
    
    return {"ok": True, "courses": result}


# ──────────────────────────────────────────────────────────────────────────────
# ENROLLMENT
# ──────────────────────────────────────────────────────────────────────────────

@router.post("/courses/{course_id}/enroll")
async def enroll_in_course(
    course_id: str,
    db: AsyncIOMotorDatabase = Depends(get_db),
    user=Depends(require_auth),
):
    """
    Enroll student in a course
    """
    user_id = user.get("id")
    
    # Check if course exists
    course = await db.dewi_lms_courses.find_one({"course_id": course_id})
    if not course:
        raise HTTPException(404, "Course not found")
    
    if course.get("status") != "active":
        raise HTTPException(400, "Course is not active")
    
    # Check if already enrolled
    existing = await db.dewi_lms_enrollments.find_one({
        "user_id": user_id,
        "course_id": course_id,
    })
    
    if existing:
        return {"ok": True, "message": "Already enrolled", "enrollment": serialize(existing)}
    
    # Create enrollment
    enrollment = {
        "enrollment_id": sid(),
        "user_id": user_id,
        "course_id": course_id,
        "status": "not_started",
        "progress_percent": 0,
        "completed_items": 0,
        "total_items": len(course.get("materials", [])),
        "enrolled_at": now_utc(),
        "enrolled_by": None,  # Self-enrollment
        "is_mandatory": False,
        "last_accessed": now_utc(),
        "completed_at": None,
    }
    
    await db.dewi_lms_enrollments.insert_one(enrollment)
    
    # Update course enrollment count
    await db.dewi_lms_courses.update_one(
        {"course_id": course_id},
        {"$inc": {"enrollment_count": 1}}
    )
    
    # Phase 3.4: Auto-create course discussion channel
    channel_id = await _auto_create_course_channel(db, course_id, course.get("title", ""), user_id)
    
    # Notification: course enrollment (mention channel if created)
    channel_info = f" Bergabunglah ke channel diskusi #course-{course.get('title','').lower()[:15]}." if channel_id else ""
    await _notify(db, user_id, 'course',
        f'Berhasil mendaftar: {course.get("title", "Course")}',
        f'Anda telah mendaftar ke course "{course.get("title", "")}". Selamat belajar!{channel_info}',
        source_type='course', source_id=course_id)
    
    return {"ok": True, "enrollment": serialize(enrollment), "channel_id": channel_id}


# ──────────────────────────────────────────────────────────────────────────────
# COURSE DETAIL & MATERIALS
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/courses/{course_id}")
async def get_course_detail(
    course_id: str,
    db: AsyncIOMotorDatabase = Depends(get_db),
    user=Depends(require_auth),
):
    """
    Get full course details with materials and student progress
    """
    user_id = user.get("id")
    
    # Get course
    course = await db.dewi_lms_courses.find_one({"course_id": course_id})
    if not course:
        raise HTTPException(404, "Course not found")
    
    # Get enrollment
    enrollment = await db.dewi_lms_enrollments.find_one({
        "user_id": user_id,
        "course_id": course_id,
    })
    
    # Get materials
    materials = await db.dewi_lms_materials.find({"course_id": course_id}).sort("order", 1).to_list(100)
    
    # Get progress for each material
    if enrollment:
        progress_records = await db.dewi_lms_progress.find({
            "enrollment_id": enrollment["enrollment_id"]
        }).to_list(200)
        
        progress_map = {p["material_id"]: p for p in progress_records}
        
        # Attach progress to materials
        for mat in materials:
            mat_id = mat["material_id"]
            if mat_id in progress_map:
                prog = progress_map[mat_id]
                mat["progress_status"] = prog.get("status")
                mat["completed_at"] = serialize(prog).get("completed_at")
                # Include quiz_score if present
                if prog.get("quiz_score") is not None:
                    mat["quiz_score"] = prog.get("quiz_score")
            else:
                mat["progress_status"] = "not_started"
                mat["completed_at"] = None
    else:
        for mat in materials:
            mat["progress_status"] = "not_started"
            mat["completed_at"] = None
    
    # Strip correct_index from quiz questions (don't leak answers to client!)
    for mat in materials:
        if mat.get("type") == "quiz" and isinstance(mat.get("questions"), list):
            safe_questions = []
            for q in mat["questions"]:
                safe_q = {
                    "question": q.get("question"),
                    "choices": q.get("choices", []),
                }
                safe_questions.append(safe_q)
            mat["questions"] = safe_questions
    
    # Build response
    course_data = serialize(course)
    course_data["materials"] = [serialize(m) for m in materials]
    course_data["enrollment"] = serialize(enrollment) if enrollment else None
    
    # Update last accessed
    if enrollment:
        await db.dewi_lms_enrollments.update_one(
            {"enrollment_id": enrollment["enrollment_id"]},
            {"$set": {"last_accessed": now_utc()}}
        )
    
    return {"ok": True, "course": course_data}


# ──────────────────────────────────────────────────────────────────────────────
# PROGRESS TRACKING
# ──────────────────────────────────────────────────────────────────────────────

@router.post("/materials/{material_id}/complete")
async def mark_material_complete(
    material_id: str,
    db: AsyncIOMotorDatabase = Depends(get_db),
    user=Depends(require_auth),
    body: dict = Body(default={}),
):
    """
    Mark a learning material as completed
    """
    user_id = user.get("id")
    
    # Get material
    material = await db.dewi_lms_materials.find_one({"material_id": material_id})
    if not material:
        raise HTTPException(404, "Material not found")
    
    course_id = material["course_id"]
    
    # Get enrollment
    enrollment = await db.dewi_lms_enrollments.find_one({
        "user_id": user_id,
        "course_id": course_id,
    })
    
    if not enrollment:
        raise HTTPException(400, "Not enrolled in this course")
    
    enrollment_id = enrollment["enrollment_id"]
    
    # Check if already completed
    existing = await db.dewi_lms_progress.find_one({
        "enrollment_id": enrollment_id,
        "material_id": material_id,
    })
    
    if existing and existing.get("status") == "completed":
        return {"ok": True, "message": "Already completed", "progress": serialize(existing)}
    
    # Mark as completed
    progress = {
        "progress_id": sid(),
        "enrollment_id": enrollment_id,
        "material_id": material_id,
        "course_id": course_id,
        "user_id": user_id,
        "status": "completed",
        "completed_at": now_utc(),
        "time_spent_seconds": body.get("time_spent_seconds", 0),
    }
    
    if existing:
        await db.dewi_lms_progress.update_one(
            {"progress_id": existing["progress_id"]},
            {"$set": progress}
        )
    else:
        await db.dewi_lms_progress.insert_one(progress)
    
    # Update enrollment progress
    total_materials = await db.dewi_lms_materials.count_documents({"course_id": course_id})
    completed_materials = await db.dewi_lms_progress.count_documents({
        "enrollment_id": enrollment_id,
        "status": "completed"
    })
    
    progress_percent = int((completed_materials / total_materials * 100)) if total_materials > 0 else 0
    
    update_data = {
        "progress_percent": progress_percent,
        "completed_items": completed_materials,
        "status": "completed" if progress_percent >= 100 else "in_progress",
    }
    
    if progress_percent >= 100:
        update_data["completed_at"] = now_utc()
    
    await db.dewi_lms_enrollments.update_one(
        {"enrollment_id": enrollment_id},
        {"$set": update_data}
    )
    
    return {"ok": True, "progress": serialize(progress), "enrollment_progress": progress_percent}


# ──────────────────────────────────────────────────────────────────────────────
# ASSIGNMENTS
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/courses/{course_id}/assignments")
async def get_course_assignments(
    course_id: str,
    db: AsyncIOMotorDatabase = Depends(get_db),
    user=Depends(require_auth),
):
    """
    Get all assignments for a course with submission status
    """
    user_id = user.get("id")
    
    # Get course
    course = await db.dewi_lms_courses.find_one({"course_id": course_id})
    if not course:
        raise HTTPException(404, "Course not found")
    
    # Get assignments (materials with type='assignment')
    assignments = await db.dewi_lms_materials.find({
        "course_id": course_id,
        "type": "assignment"
    }).sort("order", 1).to_list(50)
    
    # Get enrollment
    enrollment = await db.dewi_lms_enrollments.find_one({
        "user_id": user_id,
        "course_id": course_id,
    })
    
    if not enrollment:
        return {"ok": True, "assignments": []}
    
    # Get submissions
    assignment_ids = [a["material_id"] for a in assignments]
    submissions = await db.dewi_lms_submissions.find({
        "user_id": user_id,
        "assignment_id": {"$in": assignment_ids}
    }).to_list(len(assignment_ids))
    
    submission_map = {s["assignment_id"]: s for s in submissions}
    
    # Build response
    result = []
    for assign in assignments:
        assign_data = serialize(assign)
        assign_id = assign["material_id"]
        
        if assign_id in submission_map:
            sub = submission_map[assign_id]
            assign_data["submission"] = serialize(sub)
            assign_data["submission_status"] = "graded" if sub.get("grade") is not None else "submitted"
        else:
            assign_data["submission"] = None
            assign_data["submission_status"] = "not_submitted"
        
        result.append(assign_data)
    
    return {"ok": True, "assignments": result}


@router.post("/assignments/{assignment_id}/submit")
async def submit_assignment(
    assignment_id: str,
    db: AsyncIOMotorDatabase = Depends(get_db),
    user=Depends(require_auth),
    body: dict = Body(default={}),
):
    """
    Submit an assignment (text, file, or link)
    """
    user_id = user.get("id")
    
    # Get assignment
    assignment = await db.dewi_lms_materials.find_one({"material_id": assignment_id})
    if not assignment or assignment.get("type") != "assignment":
        raise HTTPException(404, "Assignment not found")
    
    course_id = assignment["course_id"]
    
    # Get enrollment
    enrollment = await db.dewi_lms_enrollments.find_one({
        "user_id": user_id,
        "course_id": course_id,
    })
    
    if not enrollment:
        raise HTTPException(400, "Not enrolled in this course")
    
    # Check if already submitted
    existing = await db.dewi_lms_submissions.find_one({
        "user_id": user_id,
        "assignment_id": assignment_id,
    })
    
    # Create/update submission
    submission = {
        "submission_id": existing.get("submission_id") if existing else sid(),
        "assignment_id": assignment_id,
        "course_id": course_id,
        "user_id": user_id,
        "enrollment_id": enrollment["enrollment_id"],
        "submission_type": body.get("submission_type", "text"),  # text | file | link
        "text_content": body.get("text_content"),
        "file_url": body.get("file_url"),
        "link_url": body.get("link_url"),
        "submitted_at": now_utc(),
        "grade": None,
        "max_grade": assignment.get("max_score", 100),
        "feedback": None,
        "graded_by": None,
        "graded_at": None,
    }
    
    if existing:
        await db.dewi_lms_submissions.update_one(
            {"submission_id": existing["submission_id"]},
            {"$set": submission}
        )
    else:
        await db.dewi_lms_submissions.insert_one(submission)
    
    # Notification: assignment submitted
    assign_title = assignment.get("title", "Tugas")
    await _notify(db, user_id, 'assignment',
        f'Tugas diserahkan: {assign_title}',
        'Tugas Anda telah berhasil diserahkan dan sedang menunggu penilaian.',
        source_type='course', source_id=course_id)
    
    return {"ok": True, "submission": serialize(submission)}


# ──────────────────────────────────────────────────────────────────────────────
# QUIZ SUBMISSION
# ──────────────────────────────────────────────────────────────────────────────

@router.post("/quiz/{material_id}/submit")
async def submit_quiz(
    material_id: str,
    db: AsyncIOMotorDatabase = Depends(get_db),
    user=Depends(require_auth),
    body: dict = Body(default={}),
):
    """
    Submit quiz answers and get score.
    Body: { answers: [int, int, int, ...] } (index of selected choice per question)
    """
    body = body or {}
    user_id = user.get("id")
    answers = body.get("answers", [])
    
    # Get quiz material
    material = await db.dewi_lms_materials.find_one({"material_id": material_id})
    if not material or material.get("type") != "quiz":
        raise HTTPException(404, "Quiz not found")
    
    questions = material.get("questions", [])
    if not questions:
        raise HTTPException(400, "Quiz has no questions")
    
    course_id = material["course_id"]
    
    # Get enrollment
    enrollment = await db.dewi_lms_enrollments.find_one({
        "user_id": user_id,
        "course_id": course_id,
    })
    if not enrollment:
        raise HTTPException(400, "Not enrolled in this course")
    
    # Calculate score
    total = len(questions)
    correct = 0
    detailed = []
    for idx, q in enumerate(questions):
        user_answer = answers[idx] if idx < len(answers) else None
        correct_idx = q.get("correct_index")
        is_correct = user_answer == correct_idx
        if is_correct:
            correct += 1
        detailed.append({
            "question": q.get("question"),
            "user_answer_index": user_answer,
            "correct_index": correct_idx,
            "is_correct": is_correct,
        })
    
    score = int((correct / total) * 100) if total > 0 else 0
    pass_score = material.get("pass_score", 70)
    passed = score >= pass_score
    
    # Save/update progress
    enrollment_id = enrollment["enrollment_id"]
    existing = await db.dewi_lms_progress.find_one({
        "enrollment_id": enrollment_id,
        "material_id": material_id,
    })
    
    progress_doc = {
        "progress_id": existing.get("progress_id") if existing else sid(),
        "enrollment_id": enrollment_id,
        "material_id": material_id,
        "course_id": course_id,
        "user_id": user_id,
        "status": "completed" if passed else "in_progress",
        "completed_at": now_utc() if passed else None,
        "time_spent_seconds": body.get("time_spent_seconds", 0),
        "quiz_score": score,
        "quiz_attempts": (existing.get("quiz_attempts", 0) + 1) if existing else 1,
    }
    
    if existing:
        await db.dewi_lms_progress.update_one(
            {"progress_id": existing["progress_id"]},
            {"$set": progress_doc}
        )
    else:
        await db.dewi_lms_progress.insert_one(progress_doc)
    
    # If passed, update enrollment progress
    if passed:
        total_materials = await db.dewi_lms_materials.count_documents({"course_id": course_id})
        completed_materials = await db.dewi_lms_progress.count_documents({
            "enrollment_id": enrollment_id,
            "status": "completed"
        })
        progress_percent = int((completed_materials / total_materials * 100)) if total_materials > 0 else 0
        update_data = {
            "progress_percent": progress_percent,
            "completed_items": completed_materials,
            "status": "completed" if progress_percent >= 100 else "in_progress",
        }
        if progress_percent >= 100:
            update_data["completed_at"] = now_utc()
        await db.dewi_lms_enrollments.update_one(
            {"enrollment_id": enrollment_id},
            {"$set": update_data}
        )
        # Notification: quiz graded
        mat_title = material.get("title", "Quiz")
        await _notify(db, user_id, 'grade',
            f'Quiz selesai: {mat_title} — Skor {score}%',
            f'{"Selamat, Anda lulus" if passed else "Belum lulus"}! Skor: {score}/{pass_score} minimum. {"🎉" if passed else "Coba lagi ya!"}',
            source_type='course', source_id=course_id)
        # If course completed, notify certificate
        if progress_percent >= 100:
            course_doc = await db.dewi_lms_courses.find_one({"course_id": course_id})
            course_title = course_doc.get("title", "Course") if course_doc else "Course"
            await _notify(db, user_id, 'certificate',
                f'Sertifikat diperoleh: {course_title} 🎓',
                f'Selamat! Anda telah menyelesaikan course "{course_title}" dan mendapatkan sertifikat.',
                source_type='course', source_id=course_id)
    
    return {
        "ok": True,
        "score": score,
        "correct_count": correct,
        "total_questions": total,
        "pass_score": pass_score,
        "passed": passed,
        "detailed_results": detailed,
        "attempts": progress_doc["quiz_attempts"],
    }


# ──────────────────────────────────────────────────────────────────────────────
# CERTIFICATES
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/certificates")
async def get_my_certificates(
    db: AsyncIOMotorDatabase = Depends(get_db),
    user=Depends(require_auth),
):
    """
    Get all certificates earned by the student
    """
    user_id = user.get("id")
    
    # Get completed enrollments
    completed_enrollments = await db.dewi_lms_enrollments.find({
        "user_id": user_id,
        "status": "completed"
    }).to_list(100)
    
    # Get course details
    course_ids = [e["course_id"] for e in completed_enrollments]
    courses = await db.dewi_lms_courses.find({"course_id": {"$in": course_ids}}).to_list(len(course_ids))
    course_map = {c["course_id"]: c for c in courses}
    
    # Build certificates
    certificates = []
    for enrollment in completed_enrollments:
        course = course_map.get(enrollment["course_id"])
        if not course:
            continue
        
        cert = {
            "certificate_id": f"cert-{enrollment['enrollment_id']}",
            "course_id": enrollment["course_id"],
            "course_title": course.get("title"),
            "issued_date": serialize(enrollment).get("completed_at"),
            "certificate_url": f"/certificates/{enrollment['enrollment_id']}.pdf",
            "verification_code": f"CERT-2024-{enrollment['enrollment_id'][:8].upper()}",
        }
        certificates.append(cert)
    
    # Get learning stats
    total_enrollments = await db.dewi_lms_enrollments.count_documents({"user_id": user_id})
    total_completed = len(completed_enrollments)
    
    # Calculate total learning hours (sum of course durations for completed courses)
    total_hours = sum(course_map[e["course_id"]].get("duration_hours", 0) for e in completed_enrollments if e["course_id"] in course_map)
    
    return {
        "ok": True,
        "certificates": certificates,
        "stats": {
            "total_certificates": total_completed,
            "total_courses_enrolled": total_enrollments,
            "total_learning_hours": total_hours,
        }
    }


# ──────────────────────────────────────────────────────────────────────────────
# PROGRESS & ANALYTICS
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/courses/{course_id}/progress")
async def get_course_progress(
    course_id: str,
    db: AsyncIOMotorDatabase = Depends(get_db),
    user=Depends(require_auth),
):
    """
    Get detailed progress for a specific course
    """
    user_id = user.get("id")
    
    # Get enrollment
    enrollment = await db.dewi_lms_enrollments.find_one({
        "user_id": user_id,
        "course_id": course_id,
    })
    
    if not enrollment:
        raise HTTPException(404, "Not enrolled in this course")
    
    # Get materials
    materials = await db.dewi_lms_materials.find({"course_id": course_id}).sort("order", 1).to_list(100)
    
    # Get progress records
    progress_records = await db.dewi_lms_progress.find({
        "enrollment_id": enrollment["enrollment_id"]
    }).to_list(200)
    
    progress_map = {p["material_id"]: p for p in progress_records}
    
    # Calculate module-wise progress (if materials have module_id)
    module_progress = {}
    for mat in materials:
        module_id = mat.get("module_id", "default")
        if module_id not in module_progress:
            module_progress[module_id] = {"total": 0, "completed": 0}
        
        module_progress[module_id]["total"] += 1
        if mat["material_id"] in progress_map:
            module_progress[module_id]["completed"] += 1
    
    # Get quiz scores
    quiz_scores = []
    for mat in materials:
        if mat.get("type") == "quiz" and mat["material_id"] in progress_map:
            prog = progress_map[mat["material_id"]]
            if prog.get("quiz_score") is not None:
                quiz_scores.append({
                    "title": mat.get("title", "Quiz"),
                    "score": prog.get("quiz_score", 0),
                    "max_score": mat.get("max_score", 100),
                })
    
    return {
        "ok": True,
        "enrollment": serialize(enrollment),
        "module_progress": module_progress,
        "quiz_scores": quiz_scores,
        "total_time_spent": sum(p.get("time_spent_seconds", 0) for p in progress_records),
    }
