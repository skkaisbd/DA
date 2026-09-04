"""Phase 6.2 — Learning Management System (LMS)
Modul: Kursus, Materi, Pendaftaran, Progress, Sertifikasi
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from motor.motor_asyncio import AsyncIOMotorDatabase
from database import get_db
from auth import require_auth
from datetime import datetime, timezone
from typing import Optional
import uuid
import re

router = APIRouter(prefix="/api/dewi/lms", tags=["LMS"])

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
# COURSES
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/courses")
async def list_courses(
    db: AsyncIOMotorDatabase = Depends(get_db),
    user=Depends(require_auth),
    category: Optional[str] = None,
    status: Optional[str] = None,
    q: Optional[str] = None,
    page: int = Query(1, ge=1), limit: int = Query(20, ge=1, le=200),
):
    filt = {}
    if category:
        filt["category"] = category
    if status:
        filt["status"] = status
    if q:
        filt["$or"] = [{"title": {"$regex": re.escape(q), "$options": "i"}},
                         {"description": {"$regex": re.escape(q), "$options": "i"}}]
    total = await db.dewi_lms_courses.count_documents(filt)
    docs = await db.dewi_lms_courses.find(filt).sort("created_at", -1).skip((page-1)*limit).limit(limit).to_list(limit)
    return {"ok": True, "total": total, "page": page, "limit": limit, "courses": [serialize(d) for d in docs]}

@router.post("/courses")
async def create_course(
    body: dict,
    db: AsyncIOMotorDatabase = Depends(get_db),
    user=Depends(require_auth),
):
    doc = {
        "course_id": sid(),
        "title": body.get("title", "Untitled"),
        "description": body.get("description", ""),
        "category": body.get("category", "Umum"),
        "thumbnail": body.get("thumbnail", ""),
        "duration_hours": body.get("duration_hours", 1),
        "level": body.get("level", "Beginner"),
        "instructor": body.get("instructor", ""),
        "tags": body.get("tags", []),
        "materials": [],
        "quiz_count": 0,
        "status": body.get("status", "draft"),
        "enrollment_count": 0,
        "completion_count": 0,
        "pass_score": body.get("pass_score", 70),
        "certificate_template": body.get("certificate_template", "standard"),
        "created_by": user.get("name", ""),
        "created_at": now_utc(),
        "updated_at": now_utc(),
    }
    await db.dewi_lms_courses.insert_one(doc)
    return {"ok": True, "course": serialize(doc)}

@router.get("/courses/{course_id}")
async def get_course(
    course_id: str,
    db: AsyncIOMotorDatabase = Depends(get_db),
    user=Depends(require_auth),
):
    doc = await db.dewi_lms_courses.find_one({"course_id": course_id})
    if not doc:
        raise HTTPException(404, "Course tidak ditemukan")
    # attach materials
    mats = await db.dewi_lms_materials.find({"course_id": course_id}).sort("order", 1).to_list(100)
    c = serialize(doc)
    c["materials"] = [serialize(m) for m in mats]
    return {"ok": True, "course": c}

@router.put("/courses/{course_id}")
async def update_course(
    course_id: str, body: dict,
    db: AsyncIOMotorDatabase = Depends(get_db),
    user=Depends(require_auth),
):
    allowed = ["title","description","category","thumbnail","duration_hours","level",
               "instructor","tags","status","pass_score","certificate_template"]
    upd = {k: body[k] for k in allowed if k in body}
    upd["updated_at"] = now_utc()
    await db.dewi_lms_courses.update_one({"course_id": course_id}, {"$set": upd})
    doc = await db.dewi_lms_courses.find_one({"course_id": course_id})
    return {"ok": True, "course": serialize(doc)}

@router.delete("/courses/{course_id}")
async def delete_course(
    course_id: str,
    db: AsyncIOMotorDatabase = Depends(get_db),
    user=Depends(require_auth),
):
    await db.dewi_lms_courses.delete_one({"course_id": course_id})
    await db.dewi_lms_materials.delete_many({"course_id": course_id})
    await db.dewi_lms_enrollments.delete_many({"course_id": course_id})
    return {"ok": True}

# ──────────────────────────────────────────────────────────────────────────────
# MATERIALS
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/courses/{course_id}/materials")
async def list_materials(
    course_id: str,
    db: AsyncIOMotorDatabase = Depends(get_db),
    user=Depends(require_auth),
):
    docs = await db.dewi_lms_materials.find({"course_id": course_id}).sort("order", 1).to_list(100)
    return {"ok": True, "materials": [serialize(d) for d in docs]}

@router.post("/courses/{course_id}/materials")
async def add_material(
    course_id: str, body: dict,
    db: AsyncIOMotorDatabase = Depends(get_db),
    user=Depends(require_auth),
):
    # get max order
    last = await db.dewi_lms_materials.find({"course_id": course_id}).sort("order", -1).limit(1).to_list(1)
    order = (last[0]["order"] + 1) if last else 1
    doc = {
        "material_id": sid(),
        "course_id": course_id,
        "title": body.get("title", "Materi"),
        "type": body.get("type", "text"),  # text/video/pdf/slides/quiz
        "content": body.get("content", ""),
        "content_url": body.get("content_url", ""),
        "duration_minutes": body.get("duration_minutes", 0),
        "order": order,
        "is_required": body.get("is_required", True),
        "created_at": now_utc(),
    }
    await db.dewi_lms_materials.insert_one(doc)
    await db.dewi_lms_courses.update_one({"course_id": course_id}, {"$set": {"updated_at": now_utc()}})
    return {"ok": True, "material": serialize(doc)}

@router.put("/materials/{material_id}")
async def update_material(
    material_id: str, body: dict,
    db: AsyncIOMotorDatabase = Depends(get_db),
    user=Depends(require_auth),
):
    upd = {k: body[k] for k in ["title","type","content","content_url","duration_minutes","order","is_required"] if k in body}
    await db.dewi_lms_materials.update_one({"material_id": material_id}, {"$set": upd})
    doc = await db.dewi_lms_materials.find_one({"material_id": material_id})
    return {"ok": True, "material": serialize(doc)}

@router.delete("/materials/{material_id}")
async def delete_material(
    material_id: str,
    db: AsyncIOMotorDatabase = Depends(get_db),
    user=Depends(require_auth),
):
    await db.dewi_lms_materials.delete_one({"material_id": material_id})
    return {"ok": True}

# ──────────────────────────────────────────────────────────────────────────────
# ENROLLMENTS
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/enrollments")
async def list_enrollments(
    db: AsyncIOMotorDatabase = Depends(get_db),
    user=Depends(require_auth),
    course_id: Optional[str] = None,
    employee_id: Optional[str] = None,
    status: Optional[str] = None,
    page: int = Query(1, ge=1), limit: int = Query(30, ge=1, le=200),
):
    filt = {}
    if course_id:
        filt["course_id"] = course_id
    if employee_id:
        filt["employee_id"] = employee_id
    if status:
        filt["status"] = status
    total = await db.dewi_lms_enrollments.count_documents(filt)
    docs = await db.dewi_lms_enrollments.find(filt).sort("enrolled_at", -1).skip((page-1)*limit).limit(limit).to_list(limit)
    return {"ok": True, "total": total, "enrollments": [serialize(d) for d in docs]}

@router.post("/courses/{course_id}/enroll")
async def enroll(
    course_id: str, body: dict,
    db: AsyncIOMotorDatabase = Depends(get_db),
    user=Depends(require_auth),
):
    employee_ids = body.get("employee_ids", [])
    if not employee_ids:
        raise HTTPException(400, "Pilih minimal 1 karyawan")
    
    course = await db.dewi_lms_courses.find_one({"course_id": course_id})
    if not course:
        raise HTTPException(404, "Course tidak ditemukan")
    
    enrolled = []
    # Batch: existing enrollments + employee names in single queries each
    existing_emp_ids = set()
    if employee_ids:
        async for d in db.dewi_lms_enrollments.find(
            {"course_id": course_id, "employee_id": {"$in": employee_ids}},
            {"_id": 0, "employee_id": 1}
        ):
            existing_emp_ids.add(d["employee_id"])
    emp_name_map = {}
    if employee_ids:
        async for d in db.rahaza_employees.find(
            {"employee_id": {"$in": employee_ids}}, {"_id": 0, "employee_id": 1, "name": 1}
        ):
            emp_name_map[d["employee_id"]] = d.get("name", d["employee_id"])
    for emp_id in employee_ids:
        if emp_id in existing_emp_ids:
            continue
        emp_name = emp_name_map.get(emp_id, emp_id)

        doc = {
            "enrollment_id": sid(),
            "course_id": course_id,
            "course_title": course.get("title", ""),
            "employee_id": emp_id,
            "employee_name": emp_name,
            "status": "enrolled",  # enrolled/in_progress/completed/failed
            "progress_pct": 0,
            "completed_materials": [],
            "quiz_score": None,
            "passed": False,
            "enrolled_at": now_utc(),
            "started_at": None,
            "completed_at": None,
            "certificate_issued": False,
            "certificate_no": None,
        }
        await db.dewi_lms_enrollments.insert_one(doc)
        enrolled.append(emp_id)
    
    # update enrollment count
    await db.dewi_lms_courses.update_one(
        {"course_id": course_id},
        {"$set": {"updated_at": now_utc()},
         "$inc": {"enrollment_count": len(enrolled)}}
    )
    return {"ok": True, "enrolled_count": len(enrolled), "skipped": len(employee_ids) - len(enrolled)}

@router.put("/enrollments/{enrollment_id}/progress")
async def update_progress(
    enrollment_id: str, body: dict,
    db: AsyncIOMotorDatabase = Depends(get_db),
    user=Depends(require_auth),
):
    enroll = await db.dewi_lms_enrollments.find_one({"enrollment_id": enrollment_id})
    if not enroll:
        raise HTTPException(404, "Enrollment tidak ditemukan")
    
    upd = {"updated_at": now_utc()}
    if "progress_pct" in body:
        upd["progress_pct"] = body["progress_pct"]
    if "completed_materials" in body:
        upd["completed_materials"] = body["completed_materials"]
    if "status" in body:
        upd["status"] = body["status"]
    if "quiz_score" in body:
        upd["quiz_score"] = body["quiz_score"]
    
    # handle completion
    if body.get("progress_pct", 0) >= 100 or body.get("status") == "completed":
        upd["status"] = "completed"
        upd["completed_at"] = now_utc()
        
        # get pass score
        course = await db.dewi_lms_courses.find_one({"course_id": enroll["course_id"]})
        pass_score = course.get("pass_score", 70) if course else 70
        quiz_score = body.get("quiz_score", enroll.get("quiz_score", 100))
        passed = quiz_score >= pass_score
        upd["passed"] = passed
        
        if passed and not enroll.get("certificate_issued"):
            cert_no = f"CERT-{enroll['course_id'][:6].upper()}-{enroll['employee_id'][:6].upper()}-{now_utc().strftime('%Y%m')}"
            upd["certificate_issued"] = True
            upd["certificate_no"] = cert_no

            await db.dewi_lms_courses.update_one(
                {"course_id": enroll["course_id"]}, {"$inc": {"completion_count": 1}}
            )

            # ── Notifikasi ke karyawan dan HR bahwa training selesai ──────────
            try:
                from routes.rahaza_notifications import publish_notification
                # Cari user_id karyawan
                emp = await db.rahaza_employees.find_one(
                    {"id": enroll.get("employee_id")}, {"_id": 0, "user_id": 1, "name": 1}
                )
                course_title = (course or {}).get("title", "Training")
                notif_ids = []
                if emp and emp.get("user_id"):
                    notif_ids.append(emp["user_id"])
                # HR juga
                hr_users = await db.users.find(
                    {"role": {"$in": ["hr", "superadmin"]}}, {"_id": 0, "id": 1}
                ).to_list(5)
                notif_ids.extend([u["id"] for u in hr_users])

                if notif_ids:
                    await publish_notification(
                        db,
                        type_="lms_completed",
                        severity="info",
                        title=f"Training Selesai: {course_title}",
                        message=(
                            f"{(emp or {}).get('name', enroll.get('employee_id'))} "
                            f"menyelesaikan '{course_title}' "
                            f"(skor: {quiz_score}). Sertifikat: {cert_no}"
                        ),
                        link_module="hr-lms",
                        target_user_ids=list(set(notif_ids)),
                        dedup_key=f"lms_done_{enrollment_id}",
                    )
            except Exception as ne:
                import logging
                logging.getLogger(__name__).warning(f"LMS notif failed: {ne}")
    elif enroll.get("status") == "enrolled" and body.get("progress_pct", 0) > 0:
        upd["status"] = "in_progress"
        upd["started_at"] = enroll.get("started_at") or now_utc()
    
    await db.dewi_lms_enrollments.update_one({"enrollment_id": enrollment_id}, {"$set": upd})
    doc = await db.dewi_lms_enrollments.find_one({"enrollment_id": enrollment_id})
    return {"ok": True, "enrollment": serialize(doc)}

# ──────────────────────────────────────────────────────────────────────────────
# ANALYTICS
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/analytics")
async def lms_analytics(
    db: AsyncIOMotorDatabase = Depends(get_db),
    user=Depends(require_auth),
):
    total_courses = await db.dewi_lms_courses.count_documents({})
    active_courses = await db.dewi_lms_courses.count_documents({"status": "active"})
    total_enrollments = await db.dewi_lms_enrollments.count_documents({})
    completed = await db.dewi_lms_enrollments.count_documents({"status": "completed"})
    in_progress = await db.dewi_lms_enrollments.count_documents({"status": "in_progress"})
    certs_issued = await db.dewi_lms_enrollments.count_documents({"certificate_issued": True})
    
    # category breakdown
    pipeline = [
        {"$group": {"_id": "$category", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}}
    ]
    cat_breakdown = await db.dewi_lms_courses.aggregate(pipeline).to_list(20)
    
    # top courses by enrollment
    top_courses = await db.dewi_lms_courses.find({}).sort("enrollment_count", -1).limit(5).to_list(5)
    
    return {
        "ok": True,
        "summary": {
            "total_courses": total_courses,
            "active_courses": active_courses,
            "total_enrollments": total_enrollments,
            "completed": completed,
            "in_progress": in_progress,
            "certificates_issued": certs_issued,
            "completion_rate": round(completed / total_enrollments * 100, 1) if total_enrollments else 0,
        },
        "category_breakdown": [{"category": d["_id"], "count": d["count"]} for d in cat_breakdown],
        "top_courses": [serialize(c) for c in top_courses],
    }

# ──────────────────────────────────────────────────────────────────────────────
# SEED
# ──────────────────────────────────────────────────────────────────────────────

@router.post("/seed")
async def seed_lms(
    db: AsyncIOMotorDatabase = Depends(get_db),
    user=Depends(require_auth),
):
    await db.dewi_lms_courses.delete_many({})
    await db.dewi_lms_materials.delete_many({})
    await db.dewi_lms_enrollments.delete_many({})
    
    courses = [
        {
            "course_id": "crs-001",
            "title": "Orientasi Karyawan Baru CV. Dewi Aditya",
            "description": "Pengenalan perusahaan, budaya kerja, dan prosedur dasar untuk karyawan baru.",
            "category": "Orientasi",
            "thumbnail": "",
            "duration_hours": 4,
            "level": "Beginner",
            "instructor": "HR Manager",
            "tags": ["orientasi", "karyawan baru", "SOP"],
            "quiz_count": 1,
            "status": "active",
            "enrollment_count": 8,
            "completion_count": 5,
            "pass_score": 75,
            "certificate_template": "standard",
            "created_by": "Admin",
            "created_at": now_utc(),
            "updated_at": now_utc(),
        },
        {
            "course_id": "crs-002",
            "title": "K3 & Keselamatan Kerja di Area Produksi",
            "description": "Prosedur K3, penggunaan APD, dan penanganan darurat di lantai produksi.",
            "category": "Keselamatan Kerja",
            "thumbnail": "",
            "duration_hours": 6,
            "level": "Beginner",
            "instructor": "Safety Officer",
            "tags": ["K3", "keselamatan", "APD"],
            "quiz_count": 2,
            "status": "active",
            "enrollment_count": 20,
            "completion_count": 15,
            "pass_score": 80,
            "certificate_template": "k3",
            "created_by": "Admin",
            "created_at": now_utc(),
            "updated_at": now_utc(),
        },
        {
            "course_id": "crs-003",
            "title": "Teknik Jahit Dasar & Lanjutan",
            "description": "Skill jahit untuk operator baru: pengoperasian mesin, pola dasar, jahit lurus dan lengkung.",
            "category": "Skill Produksi",
            "thumbnail": "",
            "duration_hours": 16,
            "level": "Intermediate",
            "instructor": "Senior Operator",
            "tags": ["jahit", "operator", "skill"],
            "quiz_count": 3,
            "status": "active",
            "enrollment_count": 12,
            "completion_count": 7,
            "pass_score": 70,
            "certificate_template": "skill",
            "created_by": "Admin",
            "created_at": now_utc(),
            "updated_at": now_utc(),
        },
        {
            "course_id": "crs-004",
            "title": "Leadership & Manajemen Tim",
            "description": "Kursus kepemimpinan untuk supervisor dan team leader.",
            "category": "Leadership",
            "thumbnail": "",
            "duration_hours": 8,
            "level": "Advanced",
            "instructor": "GM Operasional",
            "tags": ["leadership", "supervisor", "manajemen"],
            "quiz_count": 2,
            "status": "active",
            "enrollment_count": 5,
            "completion_count": 3,
            "pass_score": 75,
            "certificate_template": "leadership",
            "created_by": "Admin",
            "created_at": now_utc(),
            "updated_at": now_utc(),
        },
        {
            "course_id": "crs-005",
            "title": "Quality Control & Standar QC Garmen",
            "description": "Prosedur QC, standar cacat, penggunaan checklist inspeksi, dan pelaporan.",
            "category": "Quality",
            "thumbnail": "",
            "duration_hours": 8,
            "level": "Intermediate",
            "instructor": "QC Manager",
            "tags": ["QC", "kualitas", "inspeksi"],
            "quiz_count": 2,
            "status": "active",
            "enrollment_count": 10,
            "completion_count": 6,
            "pass_score": 80,
            "certificate_template": "quality",
            "created_by": "Admin",
            "created_at": now_utc(),
            "updated_at": now_utc(),
        },
    ]
    
    for c in courses:
        await db.dewi_lms_courses.insert_one(c)
    
    # Add materials for course 1
    materials_c1 = [
        {"material_id": sid(), "course_id": "crs-001", "title": "Sejarah & Profil Perusahaan", "type": "text", "content": "CV. Dewi Aditya berdiri tahun...", "content_url": "", "duration_minutes": 30, "order": 1, "is_required": True, "created_at": now_utc()},
        {"material_id": sid(), "course_id": "crs-001", "title": "Peraturan & Tata Tertib", "type": "pdf", "content": "", "content_url": "", "duration_minutes": 45, "order": 2, "is_required": True, "created_at": now_utc()},
        {"material_id": sid(), "course_id": "crs-001", "title": "Pengenalan Sistem ERP", "type": "video", "content": "", "content_url": "https://www.youtube.com/watch?v=demo", "duration_minutes": 60, "order": 3, "is_required": True, "created_at": now_utc()},
        {"material_id": sid(), "course_id": "crs-001", "title": "Quiz Orientasi", "type": "quiz", "content": "", "content_url": "", "duration_minutes": 30, "order": 4, "is_required": True, "created_at": now_utc()},
    ]
    for m in materials_c1:
        await db.dewi_lms_materials.insert_one(m)
    
    # Add some enrollments
    employees = await db.rahaza_employees.find({"status": "aktif"}).limit(8).to_list(8)
    for i, emp in enumerate(employees):
        for crs_id in ["crs-001", "crs-002"]:
            progress = [100, 100, 80, 50, 30, 10, 0][i % 7]
            status = "completed" if progress == 100 else ("in_progress" if progress > 0 else "enrolled")
            enr = {
                "enrollment_id": sid(),
                "course_id": crs_id,
                "course_title": next((c["title"] for c in courses if c["course_id"] == crs_id), ""),
                "employee_id": emp.get("employee_id", str(i)),
                "employee_name": emp.get("name", f"Karyawan {i+1}"),
                "status": status,
                "progress_pct": progress,
                "completed_materials": [],
                "quiz_score": (85 if progress == 100 else None),
                "passed": (progress == 100),
                "enrolled_at": now_utc(),
                "started_at": now_utc() if progress > 0 else None,
                "completed_at": now_utc() if progress == 100 else None,
                "certificate_issued": (progress == 100),
                "certificate_no": f"CERT-{crs_id[:6].upper()}-{i+1:04d}" if progress == 100 else None,
            }
            await db.dewi_lms_enrollments.insert_one(enr)
    
    return {"ok": True, "message": "LMS seed selesai", "courses": len(courses)}
