"""
Portal Saya - Self-Service HR
Profile, Dashboard, Leave, Overtime, Payslips, Training, Notifications
"""
from fastapi import APIRouter, Request, HTTPException, UploadFile, File
from database import get_db
from auth import require_auth, serialize_doc
from datetime import datetime, timezone, date, timedelta
from typing import Optional
import uuid
import logging
from storage import put_object, generate_storage_path

logger = logging.getLogger(__name__)
router = APIRouter(tags=["portal-hr"])

def _uid(): return str(uuid.uuid4())
def _now(): return datetime.now(timezone.utc)
def _now_iso(): return _now().isoformat()

async def _get_linked_employee(db, user_id: str):
    """Wrapper tipis di atas SSOT `utils.employee_identity` (FASE 15).

    DULU modul ini hanya melihat `users.employee_id`; kalau tautan itu belum
    dibuat, Portal Saya menampilkan halaman kosong padahal karyawannya ada
    (cocok lewat `user_id`/email). Empat modul punya versi berbeda-beda —
    sekarang semuanya memakai satu resolver.
    """
    from utils.employee_identity import resolve_my_employee
    user = await db.users.find_one({"id": user_id}, {"_id": 0})
    if not user:
        return user, None
    return user, await resolve_my_employee(db, user)

@router.get("/profile")
async def get_profile(request: Request):
    user = await require_auth(request)
    db = get_db()
    u, emp = await _get_linked_employee(db, user["id"])
    return {
        "user_id": user["id"],
        "name": u.get("name") or u.get("full_name"),
        "email": u.get("email"),
        "role": u.get("role"),
        "no_hp": u.get("no_hp", ""),
        "alamat": u.get("alamat", ""),
        "nama_panggilan": u.get("nama_panggilan", ""),
        "kontak_darurat": u.get("kontak_darurat", {}),
        "foto_url": u.get("foto_url", ""),
        "employee_id": u.get("employee_id"),
        "employee": emp,
        "is_linked": emp is not None,
    }


@router.put("/profile")
async def update_profile(request: Request):
    user = await require_auth(request)
    db = get_db()
    body = await request.json()
    allowed = ["nama_panggilan", "no_hp", "alamat", "kontak_darurat", "foto_url"]
    upd = {k: v for k, v in body.items() if k in allowed}
    upd["updated_at"] = _now_iso()
    if upd:
        await db.users.update_one({"id": user["id"]}, {"$set": upd})
    out = await db.users.find_one({"id": user["id"]}, {"_id": 0, "password": 0, "hashed_password": 0})
    return serialize_doc(out)


@router.post("/profile/photo")
async def upload_profile_photo(request: Request, file: UploadFile = File(...)):
    """Upload foto profil — replaces any previous photo."""
    user = await require_auth(request)
    db = get_db()
    data = await file.read()
    # Validate size and type
    if len(data) > 5 * 1024 * 1024:
        raise HTTPException(400, "File terlalu besar (max 5 MB)")
    ct = (file.content_type or "").lower()
    if not ct.startswith("image/"):
        raise HTTPException(400, "File harus berupa gambar (JPG, PNG, WEBP, dll)")
    # Store with unique path under profile/<user_id>/
    safe_name = file.filename or "photo.jpg"
    storage_path = generate_storage_path(f"profile/{user['id']}", safe_name)
    result = put_object(storage_path, data, ct)
    photo_url = result["url"]
    # Persist URL in user document
    await db.users.update_one(
        {"id": user["id"]},
        {"$set": {"foto_url": photo_url, "updated_at": _now_iso()}}
    )
    return {"foto_url": photo_url, "message": "Foto profil berhasil diperbarui."}


# ══════════════════════════════════════════════════════════════
# DASHBOARD STATS
# ══════════════════════════════════════════════════════════════

@router.get("/dashboard")
async def get_dashboard(request: Request):
    user = await require_auth(request)
    db = get_db()
    u, emp = await _get_linked_employee(db, user["id"])
    uid = user["id"]
    emp_id = emp["id"] if emp else None
    today_str = date.today().isoformat()
    month_start = date.today().replace(day=1).isoformat()

    # --- Leave balance ---
    leave_balance = []
    if emp_id:
        bals = await db.rahaza_leave_balances.find(
            {"employee_id": emp_id, "year": date.today().year}, {"_id": 0}
        ).to_list(20)
        lt_ids = [b.get("leave_type_id") for b in bals]
        lts = await db.rahaza_leave_types.find({"id": {"$in": lt_ids}}, {"_id": 0}).to_list(500) if lt_ids else []
        lt_map = {lt["id"]: lt for lt in lts}
        for b in bals:
            lt = lt_map.get(b.get("leave_type_id"), {})
            leave_balance.append({
                "type_name": lt.get("name", "Cuti"),
                "code": lt.get("code", ""),
                "quota": b.get("quota", 0),
                "used": b.get("used", 0),
                "remaining": b.get("quota", 0) - b.get("used", 0),
            })

    # --- Last payslip ---
    last_payslip = None
    if emp_id:
        slip = await db.rahaza_payslips.find_one(
            {"employee_id": emp_id}, {"_id": 0}, sort=[("period_from", -1)]
        )
        if slip:
            last_payslip = {
                "period": slip.get("period_from", "")[:7],
                "net_pay": slip.get("net_pay", 0),
                "gross_pay": slip.get("gross_pay", 0),
            }

    # --- Absensi bulan ini ---
    absensi = {"hadir": 0, "izin": 0, "sakit": 0, "alfa": 0, "cuti": 0}
    if emp_id:
        att_rows = await db.rahaza_attendance_events.find(
            {"employee_id": emp_id, "date": {"$gte": month_start, "$lte": today_str}}, {"_id": 0, "status": 1}
        ).to_list(100)
        for r in att_rows:
            s = r.get("status", "hadir")
            if s in absensi:
                absensi[s] += 1

    # --- Pending leave requests ---
    pending_leave = 0
    if emp_id:
        pending_leave = await db.rahaza_leave_requests.count_documents(
            {"employee_id": emp_id, "status": "pending"}
        )

    # --- Training progress ---
    training_stats = {"enrolled": 0, "completed": 0, "pct": 0}
    if emp_id:
        enrollments = await db.dewi_lms_enrollments.find(
            {"employee_id": emp_id}, {"_id": 0, "status": 1}
        ).to_list(100)
        training_stats["enrolled"] = len(enrollments)
        training_stats["completed"] = sum(1 for e in enrollments if e.get("status") == "completed")
        if training_stats["enrolled"]:
            training_stats["pct"] = round(training_stats["completed"] / training_stats["enrolled"] * 100)

    # --- KPI bulan ini ---
    # RC-27: SSOT = da_kpi_submissions (dewi_kpi_submissions = phantom). DUA varian skor:
    # seed → avg_score+employee_id; app-flow (dewi_kpi_results) → section_score+evaluatee_id.
    # Filter aman = evaluatee_id (ada di kedua varian); grade diturunkan via _grade().
    kpi_score = None
    if emp_id:
        kpi_doc = await db.da_kpi_submissions.find_one(
            {"evaluatee_id": emp_id, "status": "submitted"},
            {"_id": 0, "avg_score": 1, "section_score": 1, "period_id": 1},
            sort=[("created_at", -1)]
        )
        if kpi_doc:
            _score = kpi_doc.get("avg_score") or kpi_doc.get("section_score") or 0
            _score = float(_score)
            # Normalisasi skala: avg_score (seed) = 1-5; section_score (app) = 0-100
            _score_100 = _score * 20 if 0 < _score <= 5 else _score
            try:
                from routes.dewi_kpi_shared import _grade as _kpi_grade
                _grade_info = _kpi_grade(_score_100) if _score_100 else {"grade": "-"}
            except Exception:
                _grade_info = {"grade": "-"}
            kpi_score = {
                "score": round(_score_100, 1),
                "grade": _grade_info.get("grade", "-"),
                "period": kpi_doc.get("period_id", ""),
            }

    # --- Todo stats ---
    todos_total = await db.portal_todos.count_documents({"user_id": uid})
    todos_done  = await db.portal_todos.count_documents({"user_id": uid, "done": True})
    todos_overdue = await db.portal_todos.count_documents({
        "user_id": uid, "done": False,
        "due_date": {"$lt": today_str, "$exists": True, "$ne": ""},
    })

    # --- Upcoming reminders ---
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    upcoming_reminders = await db.portal_reminders.find(
        {"user_id": uid, "is_done": False, "remind_at": {"$lte": tomorrow + "T23:59:59"}},
        {"_id": 0}
    ).sort("remind_at", 1).to_list(5)

    return {
        "is_linked": emp is not None,
        "employee_name": emp.get("name") if emp else None,
        "employee_code": emp.get("employee_code") if emp else None,
        "job_title": emp.get("job_title") if emp else None,
        "leave_balance": leave_balance,
        "last_payslip": last_payslip,
        "absensi_bulan_ini": absensi,
        "pending_leave": pending_leave,
        "training_stats": training_stats,
        "kpi_score": kpi_score,
        "todos": {"total": todos_total, "done": todos_done, "overdue": todos_overdue},
        "upcoming_reminders": [serialize_doc(r) for r in upcoming_reminders],
    }


# ══════════════════════════════════════════════════════════════
# CUTI & IZIN
# ══════════════════════════════════════════════════════════════

@router.get("/leave")
async def my_leave(request: Request, limit: int = 30, status: Optional[str] = None):
    user = await require_auth(request)
    db = get_db()
    _, emp = await _get_linked_employee(db, user["id"])
    if not emp:
        raise HTTPException(409, "Akun belum terhubung ke data karyawan. Hubungi HR Admin.")
    q = {"employee_id": emp["id"]}
    if status:
        q["status"] = status
    rows = await db.rahaza_leave_requests.find(q, {"_id": 0}).sort("created_at", -1).limit(limit).to_list(500)
    # Enrich with leave type name
    lt_ids = list({r.get("leave_type_id") for r in rows if r.get("leave_type_id")})
    lts = await db.rahaza_leave_types.find({"id": {"$in": lt_ids}}, {"_id": 0}).to_list(500) if lt_ids else []
    lt_map = {lt["id"]: lt for lt in lts}
    for r in rows:
        lt = lt_map.get(r.get("leave_type_id"), {})
        r["leave_type_name"] = lt.get("name", "Cuti")
        r["leave_type_color"] = lt.get("color", "#6366f1")
    return {"total": len(rows), "items": rows}


@router.post("/leave")
async def create_leave(request: Request):
    user = await require_auth(request)
    db = get_db()
    _, emp = await _get_linked_employee(db, user["id"])
    if not emp:
        raise HTTPException(409, "Akun belum terhubung ke data karyawan.")
    body = await request.json()
    leave_type_id = body.get("leave_type_id")
    from_date = body.get("from_date")
    to_date = body.get("to_date", from_date)
    reason = body.get("reason", "")

    if not leave_type_id or not from_date:
        raise HTTPException(400, "leave_type_id dan from_date wajib diisi.")

    lt = await db.rahaza_leave_types.find_one({"id": leave_type_id, "active": True})
    if not lt:
        raise HTTPException(404, "Tipe cuti tidak ditemukan.")

    # Calculate days
    try:
        d1 = date.fromisoformat(from_date)
        d2 = date.fromisoformat(to_date)
        days = (d2 - d1).days + 1
    except Exception:
        raise HTTPException(400, "Format tanggal tidak valid (YYYY-MM-DD).")

    doc = {
        "id": _uid(),
        "employee_id": emp["id"],
        "employee_name": emp.get("name"),
        "leave_type_id": leave_type_id,
        "leave_type_name": lt.get("name"),
        "from_date": from_date,
        "to_date": to_date,
        "days": days,
        "reason": reason,
        "status": "pending",
        "submitted_by_self": True,
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
    }
    await db.rahaza_leave_requests.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.delete("/leave/{leave_id}")
async def cancel_leave(leave_id: str, request: Request):
    user = await require_auth(request)
    db = get_db()
    _, emp = await _get_linked_employee(db, user["id"])
    if not emp:
        raise HTTPException(409, "Akun belum terhubung.")
    lr = await db.rahaza_leave_requests.find_one({"id": leave_id, "employee_id": emp["id"]}, {"_id": 0})
    if not lr:
        raise HTTPException(404, "Request tidak ditemukan.")
    if lr.get("status") != "pending":
        raise HTTPException(400, f"Tidak dapat membatalkan request dengan status '{lr.get('status')}'.")
    await db.rahaza_leave_requests.delete_one({"id": leave_id})
    return {"ok": True}


@router.get("/leave-types")
async def get_leave_types(request: Request):
    await require_auth(request)
    db = get_db()
    types = await db.rahaza_leave_types.find({"active": True}, {"_id": 0}).sort("name", 1).to_list(500)
    return {"items": types}


# ══════════════════════════════════════════════════════════════
# LEMBUR
# ══════════════════════════════════════════════════════════════

@router.get("/overtime")
async def my_overtime(request: Request, limit: int = 30):
    user = await require_auth(request)
    db = get_db()
    _, emp = await _get_linked_employee(db, user["id"])
    if not emp:
        raise HTTPException(409, "Akun belum terhubung ke data karyawan.")
    rows = await db.rahaza_overtime_requests.find(
        {"employee_id": emp["id"]}, {"_id": 0}
    ).sort("date", -1).limit(limit).to_list(500)
    return {"total": len(rows), "items": rows}


@router.post("/overtime")
async def create_overtime(request: Request):
    user = await require_auth(request)
    db = get_db()
    _, emp = await _get_linked_employee(db, user["id"])
    if not emp:
        raise HTTPException(409, "Akun belum terhubung ke data karyawan.")
    body = await request.json()
    ot_date = body.get("date")
    start_time = body.get("start_time")
    end_time = body.get("end_time")
    reason = body.get("reason", "")
    if not ot_date or not start_time or not end_time:
        raise HTTPException(400, "date, start_time, dan end_time wajib diisi.")

    # Calculate hours
    try:
        fmt = "%H:%M"
        st = datetime.strptime(start_time, fmt)
        et = datetime.strptime(end_time, fmt)
        hours = round((et - st).total_seconds() / 3600, 2)
        if hours <= 0:
            raise HTTPException(400, "end_time harus setelah start_time.")
    except ValueError:
        raise HTTPException(400, "Format waktu tidak valid (HH:MM).")

    doc = {
        "id": _uid(),
        "employee_id": emp["id"],
        "employee_name": emp.get("name"),
        "date": ot_date,
        "start_time": start_time,
        "end_time": end_time,
        "hours": hours,
        "reason": reason,
        "status": "pending",
        "submitted_by_self": True,
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
    }
    await db.rahaza_overtime_requests.insert_one(doc)
    doc.pop("_id", None)
    return doc


# ══════════════════════════════════════════════════════════════
# PAYSLIP
# ══════════════════════════════════════════════════════════════

@router.get("/payslips")
async def my_payslips(request: Request):
    user = await require_auth(request)
    db = get_db()
    _, emp = await _get_linked_employee(db, user["id"])
    if not emp:
        raise HTTPException(409, "Akun belum terhubung ke data karyawan.")
    slips = await db.rahaza_payslips.find(
        {"employee_id": emp["id"]}, {"_id": 0}
    ).sort("period_from", -1).to_list(24)
    return {"employee": emp.get("name"), "items": slips}


# ══════════════════════════════════════════════════════════════
# TRAINING
# ══════════════════════════════════════════════════════════════

@router.get("/training")
async def my_training(request: Request):
    user = await require_auth(request)
    db = get_db()
    _, emp = await _get_linked_employee(db, user["id"])
    emp_id = emp["id"] if emp else None
    if not emp_id:
        raise HTTPException(409, "Akun belum terhubung ke data karyawan.")

    enrollments = await db.dewi_lms_enrollments.find(
        {"employee_id": emp_id}, {"_id": 0}
    ).sort("enrolled_at", -1).to_list(50)

    # Enrich with course info
    course_ids = list({e.get("course_id") for e in enrollments if e.get("course_id")})
    courses = await db.dewi_lms_courses.find({"course_id": {"$in": course_ids}}, {"_id": 0}).to_list(500) if course_ids else []
    course_map = {c["course_id"]: c for c in courses}

    items = []
    for e in enrollments:
        course = course_map.get(e.get("course_id"), {})
        items.append({
            **e,
            "course_title": course.get("title", ""),
            "course_category": course.get("category", ""),
            "total_modules": course.get("total_modules", 0),
        })

    return {"employee": emp.get("name"), "total": len(items), "items": items}


@router.get("/training/{enrollment_id}/certificate")
async def download_training_certificate(enrollment_id: str, request: Request):
    """Generate PDF sertifikat untuk kursus yang sudah selesai."""
    user = await require_auth(request)
    db = get_db()
    _, emp = await _get_linked_employee(db, user["id"])
    if not emp:
        raise HTTPException(409, "Akun belum terhubung ke data karyawan.")

    enroll = await db.dewi_lms_enrollments.find_one({"enrollment_id": enrollment_id, "employee_id": emp["id"]}, {"_id": 0})
    if not enroll:
        raise HTTPException(404, "Enrollment tidak ditemukan.")
    if enroll.get("status") != "completed":
        raise HTTPException(400, "Kursus belum selesai — sertifikat belum tersedia.")

    course = await db.dewi_lms_courses.find_one({"course_id": enroll.get("course_id")}, {"_id": 0})
    course_title = course.get("title", "Kursus") if course else "Kursus"
    completed_at_raw = enroll.get("completed_at")
    if completed_at_raw:
        if isinstance(completed_at_raw, str):
            completed_at = completed_at_raw[:10]
        else:
            # datetime object
            completed_at = completed_at_raw.strftime("%Y-%m-%d") if hasattr(completed_at_raw, 'strftime') else "N/A"
    else:
        completed_at = "N/A"
    emp_name = emp.get("name", emp.get("full_name", user.get("name", "Peserta")))

    # Generate PDF
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, HRFlowable
    from io import BytesIO

    buf = BytesIO()
    W, H = landscape(A4)
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4),
                            rightMargin=2*cm, leftMargin=2*cm, topMargin=2*cm, bottomMargin=2*cm)

    styles = getSampleStyleSheet()
    s_center = ParagraphStyle('center', parent=styles['Normal'], alignment=1, spaceAfter=6)
    s_title  = ParagraphStyle('title',  parent=s_center, fontSize=32, textColor=colors.HexColor('#4f46e5'), leading=38)
    s_sub    = ParagraphStyle('sub',    parent=s_center, fontSize=14, textColor=colors.HexColor('#64748b'), leading=18)
    s_name   = ParagraphStyle('name',   parent=s_center, fontSize=26, textColor=colors.HexColor('#1e293b'), leading=32)
    s_course = ParagraphStyle('course', parent=s_center, fontSize=20, textColor=colors.HexColor('#4f46e5'), leading=26)
    s_small  = ParagraphStyle('small',  parent=s_center, fontSize=11, textColor=colors.HexColor('#94a3b8'), leading=14)

    story = [
        Spacer(1, 0.5*cm),
        Paragraph("SERTIFIKAT PENYELESAIAN", s_title),
        Paragraph("CV. DEWI ADITYA", s_sub),
        Spacer(1, 0.6*cm),
        HRFlowable(width="80%", thickness=1, color=colors.HexColor('#e2e8f0'), spaceAfter=0.6*cm),
        Paragraph("Dengan bangga diberikan kepada:", s_small),
        Spacer(1, 0.3*cm),
        Paragraph(f"<b>{emp_name}</b>", s_name),
        Spacer(1, 0.3*cm),
        Paragraph("telah berhasil menyelesaikan kursus:", s_small),
        Spacer(1, 0.3*cm),
        Paragraph(f"<b>{course_title}</b>", s_course),
        Spacer(1, 0.5*cm),
        HRFlowable(width="60%", thickness=1, color=colors.HexColor('#e2e8f0'), spaceAfter=0.5*cm),
        Paragraph(f"Tanggal Selesai: <b>{completed_at}</b>", s_small),
        Spacer(1, 0.4*cm),
        Paragraph("CV. Dewi Aditya — ERP Training & Development", s_small),
    ]
    doc.build(story)
    buf.seek(0)

    safe = f"sertifikat_{emp_name.replace(' ', '_')}_{course_title.replace(' ', '_')[:20]}.pdf"
    from fastapi.responses import StreamingResponse
    return StreamingResponse(
        buf,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={safe}"}
    )


# ══════════════════════════════════════════════════════════════
# NOTIFICATIONS
# ══════════════════════════════════════════════════════════════

@router.get("/notifications")
async def my_notifications(request: Request, skip: int = 0, limit: int = 30):
    user = await require_auth(request)
    db = get_db()
    uid = user["id"]
    role = (user.get("role") or "").lower()

    # Read from unified SSOT `notifications` (type='rahaza') with multi-recipient
    # matching via meta.target_user_ids / meta.target_roles, plus reshape back
    # to the legacy schema for frontend compatibility.
    flt: dict = {
        'type': 'rahaza',
        'meta.dismissed': {'$ne': True},
        '$or': [
            {'meta.target_user_ids': uid},
            {'user_id': uid},
        ],
    }
    if role:
        flt['$or'].append({'meta.target_roles': role})
    if role == 'superadmin':
        # Superadmin sees everything (broadcast)
        flt.pop('$or')
    total = await db.notifications.count_documents(flt)
    cursor = (
        db.notifications.find(flt, {'_id': 0})
        .sort('created_at', -1).skip(skip).limit(limit)
    )
    from utils.notif_unified import reshape_as_rahaza as _reshape_r
    rows = [_reshape_r(d, current_user_id=uid) async for d in cursor]
    unread = sum(1 for r in rows if not r.get("read"))
    return {"total": total, "skip": skip, "limit": limit, "has_more": (skip + limit) < total, "unread": unread, "items": rows}


@router.put("/notifications/{notif_id}/read")
async def mark_read(notif_id: str, request: Request):
    user = await require_auth(request)
    db = get_db()
    uid = user["id"]
    # Multi-recipient rahaza notifs: mark this user's id into meta.read_by[]
    await db.notifications.update_one(
        {"id": notif_id, "type": "rahaza"},
        {
            "$addToSet": {"meta.read_by": uid},
            "$set": {"read_at": _now_iso()},
        },
    )
    return {"ok": True}


# ══════════════════════════════════════════════════════════════
# WORKSPACE — NOTES (Rich text notepad)
# ══════════════════════════════════════════════════════════════

