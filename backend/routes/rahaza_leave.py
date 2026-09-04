"""
PT Rahaza — Sprint 2.3: Leave Management (Izin/Cuti)
Fase 2 — Enhanced per UU No. 13 Tahun 2003

Collections:
  - rahaza_leave_types:    Master tipe cuti (request_type: cuti|sakit|izin, requires_document)
  - rahaza_leave_requests: Request cuti/izin/sakit karyawan
  - rahaza_leave_balances: Saldo cuti per karyawan per tahun

New fields in leave_request:
  - request_type: "cuti" | "sakit" | "izin"
  - attachment_url: URL bukti dokumen (wajib untuk leave_type.requires_document)
  - attachment_filename: nama file asli
  - is_half_day: bool
  - half_day_period: "AM" | "PM"
  - duration_working_days: hari kerja (tanpa Sabtu/Minggu)

New endpoints:
  - POST /leaves/upload-document  → upload bukti
  - POST /leaves/{id}/cancel      → batalkan cuti approved (kembalikan saldo)
"""
# ruff: noqa: E741
from fastapi import APIRouter, Request, HTTPException, UploadFile, File
from database import get_db
from auth import require_auth, serialize_doc, log_activity
import uuid
import re
import logging
from datetime import datetime, timezone, date, timedelta
from typing import Optional
from utils.waktu import wib_year

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/rahaza", tags=["rahaza-leave"])


from object_storage import put_object as _put_object
ALLOWED_MIMES = {"image/jpeg", "image/png", "image/webp", "image/jpg",
                 "application/pdf", "image/heic"}
MAX_FILE_BYTES = 8 * 1024 * 1024  # 8 MB


def _uid(): return str(uuid.uuid4())
def _now(): return datetime.now(timezone.utc)


def _count_working_days(d_from: date, d_to: date) -> int:
    """Hitung hari kerja (Senin–Jumat) antara dua tanggal. Tanpa exclude libur nasional."""
    count = 0
    cur = d_from
    while cur <= d_to:
        if cur.weekday() < 5:
            count += 1
        cur += timedelta(days=1)
    return count


async def _count_working_days_db(db, d_from: date, d_to: date) -> dict:
    """
    Hitung hari kerja exclude Sabtu/Minggu DAN libur nasional dari production_calendar.
    Returns dict: { working_days, calendar_days, weekend_days, holiday_days, holidays: [list] }
    """
    # Fetch holidays in range from production calendar
    from_iso = d_from.isoformat()
    to_iso   = d_to.isoformat()
    hol_docs = await db.rahaza_production_calendar.find(
        {"date": {"$gte": from_iso, "$lte": to_iso}, "type": "holiday"},
        {"_id": 0, "date": 1, "name": 1}
    ).to_list(100)
    holiday_set  = {h["date"] for h in hol_docs}
    holiday_list = [{"date": h["date"], "name": h["name"]} for h in hol_docs]

    calendar_days = working_days = weekend_days = holiday_days = 0
    cur = d_from
    while cur <= d_to:
        calendar_days += 1
        iso = cur.isoformat()
        is_weekend = cur.weekday() >= 5
        is_holiday = iso in holiday_set and not is_weekend  # holiday on weekday

        if is_weekend:
            weekend_days += 1
        elif is_holiday:
            holiday_days += 1
        else:
            working_days += 1
        cur += timedelta(days=1)

    return {
        "working_days":   working_days,
        "calendar_days":  calendar_days,
        "weekend_days":   weekend_days,
        "holiday_days":   holiday_days,
        "holidays":       sorted(holiday_list, key=lambda x: x["date"]),
    }


def _safe_ext(filename: str) -> str:
    if not filename or '.' not in filename:
        return 'jpg'
    ext = filename.rsplit('.', 1)[-1].lower()
    ext = re.sub(r'[^a-z0-9]', '', ext)
    return ext if ext in {'jpg', 'jpeg', 'png', 'webp', 'pdf', 'heic'} else 'jpg'


LEAVE_STATUSES = ["draft", "pending_approval", "approved", "rejected", "cancelled"]


# ── BUG-4 (2026-07-26): "dibayar / tidak" punya DUA nama field di koleksi yang
# SAMA (`unpaid` dari seeder, `paid` dari form HR). Semua pembaca di berkas ini
# WAJIB lewat SSOT `utils/leave_types` supaya "Cuti Tahunan" tidak lagi
# dilaporkan sebagai cuti tidak berbayar.
def _lt_is_paid(lt) -> bool:
    from utils.leave_types import is_paid
    return is_paid(lt)


def _lt_is_unpaid(lt) -> bool:
    from utils.leave_types import is_unpaid
    return is_unpaid(lt)


async def _require_hr_admin(request: Request):
    """Require HR, admin, or owner."""
    user = await require_auth(request)
    role = (user.get("role") or "").lower()
    if role in ("superadmin", "admin", "owner", "hr"):
        return user
    perms = user.get("_permissions") or []
    if "*" in perms or "hr.manage" in perms:
        return user
    raise HTTPException(403, "Forbidden: butuh akses HR/Admin.")


async def _require_leave_approver(request: Request):
    """Require manager, HR, or owner for approval."""
    user = await require_auth(request)
    role = (user.get("role") or "").lower()
    if role in ("superadmin", "owner", "manager", "hr", "production_manager"):
        return user
    perms = user.get("_permissions") or []
    if "*" in perms or "hr.approve" in perms:
        return user
    raise HTTPException(403, "Forbidden: hanya Manager/HR yang boleh approve cuti.")


# ── LEAVE TYPES (Master) ───────────────────────────────────────────────────────

@router.get("/leave-types")
async def list_leave_types(request: Request):
    await require_auth(request)
    db = get_db()
    rows = await db.rahaza_leave_types.find({}, {"_id": 0}).sort("code", 1).to_list(500)
    # SSOT bentuk (BUG-4): `paid`/`unpaid` selalu sinkron, field wajib tak pernah hilang
    from utils.leave_types import public_leave_type
    return serialize_doc([public_leave_type(r) for r in rows])


@router.post("/leave-types")
async def create_leave_type(request: Request):
    """Buat jenis/alasan cuti baru.

    BUG-4 (2026-07-26): endpoint ini dulu HANYA menyimpan `code`, `name`, `paid`,
    `quota_default`, `description` — padahal form HR mengirim `request_type`,
    `requires_document`, `max_days_without_doc`, `doc_note`. Semua itu dibuang
    diam-diam, jadi jenis cuti buatan HR tidak pernah bisa mewajibkan dokumen dan
    selalu dianggap 'cuti'. Sekarang seluruh dokumen dibentuk SSOT
    `utils/leave_types.build_leave_type_doc`.
    """
    user = await _require_hr_admin(request)
    db = get_db()
    body = await request.json()

    from utils.leave_types import build_leave_type_doc, public_leave_type
    doc = build_leave_type_doc(body)

    if await db.rahaza_leave_types.find_one({"code": doc["code"], "active": True}):
        raise HTTPException(409, f"Kode '{doc['code']}' sudah terpakai.")

    doc.update({"id": _uid(), "created_at": _now()})
    await db.rahaza_leave_types.insert_one(dict(doc))
    await log_activity(user["id"], user.get("name", ""), "create", "rahaza.leave_type", doc["code"])
    return serialize_doc(public_leave_type(doc))


@router.put("/leave-types/{lt_id}")
async def update_leave_type(lt_id: str, request: Request):
    """Ubah jenis cuti.

    BUG-4: dulu `$set` seluruh body MENTAH — bisa menulis field sembarang,
    menduplikasi `code`, atau mematikan `active` tanpa validasi.
    """
    user = await _require_hr_admin(request)
    db = get_db()
    body = await request.json()

    existing = await db.rahaza_leave_types.find_one({"id": lt_id}, {"_id": 0})
    if not existing:
        raise HTTPException(404, "Leave type tidak ditemukan.")

    from utils.leave_types import build_leave_type_doc, public_leave_type
    doc = build_leave_type_doc(body, existing)

    if doc["code"] != existing.get("code"):
        dup = await db.rahaza_leave_types.find_one(
            {"code": doc["code"], "active": True, "id": {"$ne": lt_id}})
        if dup:
            raise HTTPException(409, f"Kode '{doc['code']}' sudah terpakai.")

    await db.rahaza_leave_types.update_one({"id": lt_id}, {"$set": doc})
    await log_activity(user["id"], user.get("name", ""), "update", "rahaza.leave_type", lt_id)
    fresh = await db.rahaza_leave_types.find_one({"id": lt_id}, {"_id": 0})
    return serialize_doc(public_leave_type(fresh))


@router.delete("/leave-types/{lt_id}")
async def deactivate_leave_type(lt_id: str, request: Request):
    """Nonaktifkan jenis cuti (tidak dihapus — riwayat pengajuan harus tetap terbaca)."""
    await _require_hr_admin(request)
    db = get_db()
    lt = await db.rahaza_leave_types.find_one({"id": lt_id}, {"_id": 0})
    if not lt:
        raise HTTPException(404, "Leave type tidak ditemukan.")
    pending = await db.rahaza_leave_requests.count_documents(
        {"leave_type_id": lt_id, "status": {"$in": ["draft", "pending_approval"]}})
    if pending:
        raise HTTPException(
            409, f"Masih ada {pending} pengajuan berstatus menunggu memakai jenis ini. "
                 "Proses dulu pengajuannya sebelum menonaktifkan.")
    await db.rahaza_leave_types.update_one({"id": lt_id}, {"$set": {"active": False, "updated_at": _now()}})
    return {"status": "deactivated", "ok": True}


# ── WORKING DAYS PREVIEW ──────────────────────────────────────────────────────

@router.get("/leaves/working-days")
async def working_days_preview(
    request: Request,
    from_date: str,
    to_date: str,
):
    """
    Preview hari kerja antara dua tanggal.
    Exclude Sabtu/Minggu + libur nasional dari production_calendar.
    Dipakai frontend untuk live-update saat user pilih tanggal.
    """
    await require_auth(request)
    db = get_db()
    try:
        d_from = date.fromisoformat(from_date)
        d_to   = date.fromisoformat(to_date)
        if d_to < d_from:
            raise HTTPException(400, "to_date harus >= from_date")
    except ValueError:
        raise HTTPException(400, "Format tanggal tidak valid (YYYY-MM-DD)")

    info = await _count_working_days_db(db, d_from, d_to)
    return {
        "from_date":      from_date,
        "to_date":        to_date,
        "calendar_days":  info["calendar_days"],
        "working_days":   info["working_days"],
        "weekend_days":   info["weekend_days"],
        "holiday_days":   info["holiday_days"],
        "holidays":       info["holidays"],
        "summary": (
            f"{info['working_days']} hari kerja"
            + (f" (dari {info['calendar_days']} hari kalender"
               + (f", {info['weekend_days']} akhir pekan" if info['weekend_days'] else "")
               + (f", {info['holiday_days']} libur nasional" if info['holiday_days'] else "")
               + ")")
            if info['calendar_days'] != info['working_days'] else
            f"{info['working_days']} hari kerja"
        ),
    }


# ── DOCUMENT UPLOAD ────────────────────────────────────────────────────────────

@router.post("/leaves/upload-document")
async def upload_leave_document(
    request: Request,
    file: UploadFile = File(...),
):
    """Upload bukti dokumen untuk izin/cuti. Return URL yang disimpan di leave_request."""
    user = await require_auth(request)

    if file.content_type not in ALLOWED_MIMES:
        raise HTTPException(415, "Tipe file tidak didukung. Gunakan JPG, PNG, PDF, atau WEBP.")

    data = await file.read()
    if len(data) > MAX_FILE_BYTES:
        raise HTTPException(413, f"Ukuran file melebihi {MAX_FILE_BYTES // (1024*1024)}MB.")
    if len(data) < 100:
        raise HTTPException(400, "File terlalu kecil / tidak valid.")

    ext = _safe_ext(file.filename or "")
    fid = _uid()
    fname = f"{fid}.{ext}"
    try:
        url = _put_object(f"leave_docs/{fname}", data, file.content_type or "application/octet-stream")["url"]
    except Exception as e:
        raise HTTPException(503, f"Penyimpanan berkas tidak tersedia: {e}")
    log.info(f"[leave_doc] uploaded {fname} by {user.get('id')}")
    return {
        "url": url,
        "filename": file.filename or fname,
        "size": len(data),
        "content_type": file.content_type,
    }

@router.get("/leaves")
async def list_leaves(
    request: Request,
    status: Optional[str] = None,
    employee_id: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    skip: int = 0,
    limit: int = 30,
):
    await require_auth(request)
    db = get_db()
    q = {}
    if status:
        if status not in LEAVE_STATUSES:
            raise HTTPException(400, f"Status harus: {LEAVE_STATUSES}")
        q["status"] = status
    if employee_id:
        q["employee_id"] = employee_id
    if date_from:
        q["from_date"] = q.get("from_date", {})
        q["from_date"]["$gte"] = date_from
    if date_to:
        q["to_date"] = q.get("to_date", {})
        q["to_date"]["$lte"] = date_to

    total = await db.rahaza_leave_requests.count_documents(q)
    rows = await db.rahaza_leave_requests.find(q, {"_id": 0}).sort("created_at", -1).skip(skip).limit(limit).to_list(500)

    # Enrich with employee & leave type names
    emp_ids = list({r["employee_id"] for r in rows if r.get("employee_id")})
    lt_ids = list({r["leave_type_id"] for r in rows if r.get("leave_type_id")})
    
    emps = await db.rahaza_employees.find({"id": {"$in": emp_ids}}, {"_id": 0}).to_list(500) if emp_ids else []
    lts = await db.rahaza_leave_types.find({"id": {"$in": lt_ids}}, {"_id": 0}).to_list(500) if lt_ids else []
    
    emp_map = {e["id"]: e for e in emps}
    lt_map = {l["id"]: l for l in lts}
    
    for r in rows:
        e = emp_map.get(r.get("employee_id")) or {}
        lt = lt_map.get(r.get("leave_type_id")) or {}
        r["employee_code"]  = e.get("employee_code")
        r["employee_name"]  = e.get("name")
        r["employee_dept"]  = e.get("department")
        r["manager_id"]     = e.get("manager_id")
        r["manager_name"]   = None
        r["leave_type_code"] = lt.get("code")
        r["leave_type_name"] = lt.get("name")
        r["leave_type_request_type"] = lt.get("request_type")
        r["is_paid"]        = _lt_is_paid(lt)   # BUG-4: dulu membaca field `paid` mentah

    return {
        "total": total,
        "skip": skip,
        "limit": limit,
        "has_more": (skip + limit) < total,
        "items": serialize_doc(rows),
    }


# ── LEAVE BALANCE ──────────────────────────────────────────────────────────────

@router.get("/leaves/balance")
async def get_leave_balance(request: Request, employee_id: str, year: Optional[int] = None):
    """Get leave balance for employee (per year, per leave type)."""
    await require_auth(request)
    db = get_db()
    
    if not year:
        year = wib_year()
    
    # Get all leave types
    leave_types = await db.rahaza_leave_types.find({"active": True}, {"_id": 0}).to_list(500)
    
    # Get approved leaves for this employee/year
    leaves = await db.rahaza_leave_requests.find({
        "employee_id": employee_id,
        "status": "approved",
        "from_date": {"$regex": f"^{year}"},
    }, {"_id": 0}).to_list(500)
    
    # Calculate used per leave type
    used_map = {}
    for lv in leaves:
        lt_id = lv.get("leave_type_id")
        if lt_id:
            used_map[lt_id] = used_map.get(lt_id, 0) + lv.get("duration_days", 0)
    
    # Build balance report
    balances = []
    for lt in leave_types:
        quota = lt.get("quota_default", 12)
        used = used_map.get(lt["id"], 0)
        remaining = max(0, quota - used)
        
        balances.append({
            "leave_type_id": lt["id"],
            "leave_type_code": lt["code"],
            "leave_type_name": lt["name"],
            "quota": quota,
            "used": used,
            "remaining": remaining,
            "is_paid": _lt_is_paid(lt),   # BUG-4: dokumen seeder hanya punya `unpaid`
        })
    
    return {
        "employee_id": employee_id,
        "year": year,
        "balances": balances,
    }


@router.get("/leaves/{leave_id}")
async def get_leave(leave_id: str, request: Request):
    await require_auth(request)
    db = get_db()
    leave = await db.rahaza_leave_requests.find_one({"id": leave_id}, {"_id": 0})
    if not leave:
        raise HTTPException(404, "Leave request tidak ditemukan.")
    
    # Enrich
    if leave.get("employee_id"):
        emp = await db.rahaza_employees.find_one({"id": leave["employee_id"]}, {"_id": 0})
        leave["employee_code"] = emp.get("employee_code") if emp else None
        leave["employee_name"] = emp.get("name") if emp else None
    if leave.get("leave_type_id"):
        lt = await db.rahaza_leave_types.find_one({"id": leave["leave_type_id"]}, {"_id": 0})
        leave["leave_type_code"] = lt.get("code") if lt else None
        leave["leave_type_name"] = lt.get("name") if lt else None
        leave["is_paid"] = _lt_is_paid(lt) if lt else False
    
    return serialize_doc(leave)


@router.post("/leaves/request")
async def request_leave(request: Request):
    """Create leave/permit request (langsung pending_approval)."""
    user = await require_auth(request)
    db = get_db()
    body = await request.json()

    employee_id    = body.get("employee_id")
    leave_type_id  = body.get("leave_type_id")
    from_date      = body.get("from_date")
    to_date        = body.get("to_date")
    reason         = (body.get("reason") or "").strip()
    attachment_url  = body.get("attachment_url") or ""
    attachment_filename = body.get("attachment_filename") or ""
    is_half_day    = bool(body.get("is_half_day", False))
    half_day_period= body.get("half_day_period") or "AM"  # AM | PM
    request_type   = body.get("request_type") or ""  # cuti | sakit | izin (auto dari leave_type)

    if not (employee_id and leave_type_id and from_date and to_date):
        raise HTTPException(400, "employee_id, leave_type_id, from_date, to_date wajib diisi.")

    # Validate employee & leave type
    emp = await db.rahaza_employees.find_one({"id": employee_id})
    if not emp:
        raise HTTPException(404, "Employee tidak ditemukan.")

    lt = await db.rahaza_leave_types.find_one({"id": leave_type_id, "active": True})
    if not lt:
        raise HTTPException(404, "Leave type tidak ditemukan atau tidak aktif.")

    # Calculate duration
    try:
        d_from = date.fromisoformat(from_date)
        d_to   = date.fromisoformat(to_date)
        if d_to < d_from:
            raise HTTPException(400, "to_date tidak boleh lebih awal dari from_date.")
        if is_half_day:
            duration = 0.5
            duration_working = 0.5
            holidays_in_period = []
        else:
            duration = (d_to - d_from).days + 1
            wd_info  = await _count_working_days_db(db, d_from, d_to)
            duration_working   = wd_info["working_days"]
            holidays_in_period = wd_info["holidays"]
    except ValueError:
        raise HTTPException(400, "Format tanggal tidak valid (YYYY-MM-DD).")

    # Guard (NEW-BUG-5): tolak pengajuan cuti yang TUMPANG-TINDIH dgn pengajuan aktif employee yang sama.
    # Overlap: existing.from_date <= to_date AND existing.to_date >= from_date.
    overlap = await db.rahaza_leave_requests.find_one({
        "employee_id": employee_id,
        "status": {"$nin": ["cancelled", "rejected"]},
        "from_date": {"$lte": to_date},
        "to_date": {"$gte": from_date},
    })
    if overlap:
        raise HTTPException(
            400,
            f"Pengajuan cuti tumpang-tindih dengan pengajuan aktif "
            f"({overlap.get('from_date')} s/d {overlap.get('to_date')}, status {overlap.get('status')}).",
        )

    # Validate document requirement
    requires_doc      = bool(lt.get("requires_document", False))
    max_days_no_doc   = int(lt.get("max_days_without_doc", 0))
    if requires_doc:
        # Sakit: boleh sampai max_days_without_doc tanpa dokumen
        if max_days_no_doc > 0 and duration <= max_days_no_doc:
            pass  # OK without document
        elif not attachment_url:
            doc_note = lt.get("doc_note") or "Lampirkan bukti/dokumen pendukung."
            raise HTTPException(400, f"Dokumen wajib dilampirkan untuk '{lt.get('name')}'. {doc_note}")

    # Auto-set request_type from leave_type if not provided
    if not request_type:
        request_type = lt.get("request_type") or "cuti"

    # Tentukan berapa level approval yang dibutuhkan
    # > 7 hari kerja → butuh 2 level (supervisor → HR)
    approval_level_required = 2 if (not is_half_day and duration_working > 7) else 1

    doc = {
        "id":                 _uid(),
        "employee_id":        employee_id,
        "leave_type_id":      leave_type_id,
        "request_type":       request_type,
        "from_date":          from_date,
        "to_date":            to_date,
        "duration_days":      duration,
        "duration_working_days": duration_working,
        "holidays_in_period": holidays_in_period,
        "is_half_day":        is_half_day,
        "half_day_period":    half_day_period if is_half_day else None,
        "reason":             reason,
        "attachment_url":     attachment_url,
        "attachment_filename": attachment_filename,
        "status":             "pending_approval",
        "approval_level_required": approval_level_required,
        "current_approval_level":  1,
        "approval_step_1":    None,  # filled when supervisor approves
        "approval_step_2":    None,  # filled when HR approves (if needed)
        "submitted_at":       _now(),
        "submitted_by":       user["id"],
        "created_by":         user["id"],
        "created_by_name":    user.get("name", ""),
        "created_at":         _now(),
        "updated_at":         _now(),
    }
    await db.rahaza_leave_requests.insert_one(doc)
    await log_activity(user["id"], user.get("name", ""), "request", "rahaza.leave",
                       f"{emp.get('name', employee_id)} - {request_type} {duration} hari")

    # ── Task 2.4: Auto-create multi-level approval_request (non-blocking) ─────────
    try:
        from services.approval_chain_service import create_approval_request as _car
        await _car(
            db,
            req_type="leave",
            ref_id=doc["id"],
            ref_code=doc["id"],
            requester={
                "id": user["id"],
                "name": emp.get("name") or user.get("name", ""),
                "full_name": emp.get("name", ""),
                "email": user.get("email", ""),
            },
            meta={
                "employee_id": employee_id,
                "employee_name": emp.get("name", ""),
                "leave_type": lt.get("name", ""),
                "from_date": from_date,
                "to_date": to_date,
                "duration_days": duration,
                "reason": reason,
                "link_module": "hr-leave",
            },
            subject=f"Cuti {lt.get('name', '')} — {emp.get('name', '')} ({from_date} s/d {to_date})",
        )
    except Exception as _e:
        # Non-blocking: jika belum ada chain 'leave', gunakan legacy flow
        log.warning(f"[leave] auto approval_request skipped (chain belum ada?): {_e}")

    # ── Notifikasi ke manager langsung + HR ──────────────────────────────────────
    try:
        from routes.rahaza_notifications import publish_notification
        notify_ids = []

        # Manager langsung dari employee record
        manager_id = emp.get("manager_id") or emp.get("supervisor_id")
        if manager_id:
            notify_ids.append(manager_id)

        # HR users sebagai fallback/tambahan
        hr_users = await db.users.find(
            {"role": {"$in": ["hr", "superadmin", "admin", "owner"]}},
            {"_id": 0, "id": 1}
        ).to_list(10)
        for u2 in hr_users:
            if u2["id"] not in notify_ids:
                notify_ids.append(u2["id"])

        if notify_ids:
            level_label = " (butuh 2 level persetujuan)" if approval_level_required == 2 else ""
            await publish_notification(
                db,
                type_="leave_request_submitted",
                severity="info",
                title=f"Request Cuti: {emp.get('name','')} — {lt.get('name','')}",
                message=(
                    f"{emp.get('name','')} mengajukan {lt.get('name','')} "
                    f"selama {duration} hari "
                    f"({doc['from_date']} s/d {doc['to_date']}){level_label}."
                ),
                link_module="hr-leave",
                link_id=doc["id"],
                target_user_ids=notify_ids,
                dedup_key=f"leave_submitted_{doc['id']}",
            )
    except Exception as ne:
        log.warning(f"[leave] notif failed: {ne}")

    return serialize_doc(doc)


@router.post("/leaves/{leave_id}/approve")
async def approve_leave(leave_id: str, request: Request):
    """Approve leave request and auto-create attendance records."""
    user = await _require_leave_approver(request)
    db = get_db()
    
    leave = await db.rahaza_leave_requests.find_one({"id": leave_id}, {"_id": 0})
    if not leave:
        raise HTTPException(404, "Leave request tidak ditemukan.")
    if leave.get("status") not in ("pending_approval", "pending_hr_approval"):
        raise HTTPException(400, f"Hanya leave Pending Approval yang bisa di-approve. Status: {leave.get('status')}")

    approval_level_required = leave.get("approval_level_required", 1)
    current_level           = leave.get("current_approval_level", 1)

    # ─── Multi-level: apakah masih perlu ke step berikutnya? ─────────────────────
    # Step 1 (supervisor/manager): status pending_approval, current_level == 1
    # Step 2 (HR): status pending_hr_approval, current_level == 2
    step_key = f"approval_step_{current_level}"
    step_data = {
        "step":           current_level,
        "approver_id":    user["id"],
        "approver_name":  user.get("name", ""),
        "action":         "approved",
        "notes":          "",
        "at":             _now(),
    }

    if approval_level_required > 1 and current_level == 1:
        # Step 1 selesai — naik ke HR (pending_hr_approval)
        await db.rahaza_leave_requests.update_one(
            {"id": leave_id},
            {"$set": {
                step_key:                 step_data,
                "status":                 "pending_hr_approval",
                "current_approval_level": 2,
                "updated_at":             _now(),
            }}
        )
        # Notifikasi ke HR
        try:
            from routes.rahaza_notifications import publish_notification
            hr_users = await db.users.find(
                {"role": {"$in": ["hr", "superadmin", "admin"]}}, {"_id": 0, "id": 1}
            ).to_list(20)
            hr_ids = [u["id"] for u in hr_users]
            emp = await db.rahaza_employees.find_one({"id": leave["employee_id"]}, {"_id": 0, "name": 1})
            if hr_ids:
                await publish_notification(
                    db,
                    type_="leave_hr_approval_needed",
                    severity="info",
                    title=f"Persetujuan HR Dibutuhkan: Cuti {(emp or {}).get('name','')}",
                    message=f"Cuti {leave.get('duration_working_days',leave.get('duration_days'))} hari kerja telah disetujui supervisor. Butuh persetujuan HR.",
                    link_module="hr-leave",
                    link_id=leave_id,
                    target_user_ids=hr_ids,
                    dedup_key=f"leave_hr_{leave_id}",
                )
        except Exception as ne:
            log.warning(f"notif failed for leave HR step: {ne}")

        out = await db.rahaza_leave_requests.find_one({"id": leave_id}, {"_id": 0})
        return serialize_doc(out)

    # ─── Approve final (step 1 single OR step 2 HR) ──────────────────────────────
    # Validate leave balance (hanya saat final approve)
    try:
        d_from_check = date.fromisoformat(leave["from_date"])
        year = d_from_check.year
        bal = await db.rahaza_leave_balances.find_one({
            "employee_id": leave["employee_id"],
            "leave_type_id": leave["leave_type_id"],
            "year": year,
        }, {"_id": 0})
        if bal:
            remaining = int(bal.get("allocated", 0)) - float(bal.get("used", 0))
            lt_check  = await db.rahaza_leave_types.find_one({"id": leave["leave_type_id"]}, {"_id": 0})
            unpaid    = _lt_is_unpaid(lt_check)   # BUG-4: SSOT dua-field
            duration  = float(leave.get("duration_days", 1))
            if remaining < duration and not unpaid:
                raise HTTPException(400, f"Sisa cuti tidak cukup. Sisa: {remaining} hari, diminta: {duration} hari.")
    except HTTPException:
        raise
    except Exception as e:
        log.warning(f"Balance validation failed (continuing): {e}")
    
    # Update leave status → approved
    await db.rahaza_leave_requests.update_one(
        {"id": leave_id},
        {
            "$set": {
                step_key:               step_data,
                "status":               "approved",
                "approved_at":          _now(),
                "approved_by":          user["id"],
                "approved_by_name":     user.get("name", ""),
                "updated_at":           _now(),
            }
        }
    )
    
    # Auto-create attendance records (cuti) for date range
    try:
        d_from = date.fromisoformat(leave["from_date"])
        d_to = date.fromisoformat(leave["to_date"])
        
        # Get leave type for attendance status mapping
        lt = await db.rahaza_leave_types.find_one({"id": leave["leave_type_id"]}, {"_id": 0})
        ((lt or {}).get("code") or "CUTI").lower()  # null-safe: jangan sampai men-skip consume_balance

        # ─── Auto-deduct leave balance (P0.3) ──────────────────────────────────
        try:
            from routes.rahaza_leave_balances import consume_balance
            await consume_balance(
                db,
                leave["employee_id"],
                leave["leave_type_id"],
                d_from.year,
                leave.get("duration_days", 1),
            )
        except Exception as e:
            log.error(f"Failed to consume leave balance: {e}")
        
        current = d_from
        while current <= d_to:
            # Upsert attendance (overwrite if exists)
            await db.rahaza_attendance_events.update_one(
                {"employee_id": leave["employee_id"], "date": current.isoformat()},
                {
                    "$set": {
                        "status": "cuti",  # atau bisa disesuaikan dengan lt_code
                        "notes": f"Cuti: {lt.get('name') if lt else 'Leave'} ({leave.get('reason', '')})",
                        "leave_request_id": leave_id,
                        "updated_at": _now(),
                    },
                    "$setOnInsert": {
                        "id": _uid(),
                        "employee_id": leave["employee_id"],
                        "date": current.isoformat(),
                        "created_at": _now(),
                    },
                },
                upsert=True,
            )
            current += timedelta(days=1)
        
        log.info(f"Leave approved: {leave_id}, attendance created for {leave['duration_days']} days")
    except Exception as e:
        log.error(f"Failed to create attendance for leave {leave_id}: {e}")
        # Non-fatal: leave sudah approved, attendance bisa di-fix manual
    
    await log_activity(user["id"], user.get("name", ""), "approve", "rahaza.leave", leave_id)

    # ── RC-IA-1a: Notifikasi ke KARYAWAN bahwa cuti disetujui + sisa saldo ───────
    try:
        from routes.rahaza_notifications import publish_notification
        emp_users = await db.users.find(
            {"employee_id": leave["employee_id"]}, {"_id": 0, "id": 1}
        ).to_list(5)
        emp_user_ids = [u["id"] for u in emp_users]
        if emp_user_ids:
            lt_notif = await db.rahaza_leave_types.find_one({"id": leave["leave_type_id"]}, {"_id": 0})
            lt_name = (lt_notif or {}).get("name", "Cuti")
            # Sisa saldo terkini (setelah konsumsi saldo di atas)
            saldo_txt = ""
            try:
                d_year = date.fromisoformat(leave["from_date"]).year
                bal_after = await db.rahaza_leave_balances.find_one({
                    "employee_id": leave["employee_id"],
                    "leave_type_id": leave["leave_type_id"],
                    "year": d_year,
                }, {"_id": 0})
                if bal_after:
                    sisa = float(bal_after.get("allocated", 0)) - float(bal_after.get("used", 0))
                    sisa_disp = int(sisa) if float(sisa).is_integer() else round(sisa, 1)
                    saldo_txt = f" Sisa saldo {lt_name}: {sisa_disp} hari."
            except Exception:
                logging.getLogger(__name__).debug("suppressed exception", exc_info=True)
            await publish_notification(
                db,
                type_="leave_approved",
                severity="success",
                title=f"Cuti Disetujui — {lt_name}",
                message=(
                    f"Pengajuan {lt_name} Anda "
                    f"({leave.get('from_date')} s/d {leave.get('to_date')}, "
                    f"{leave.get('duration_days')} hari) telah DISETUJUI.{saldo_txt}"
                ),
                link_module="portal-cuti",
                link_id=leave_id,
                target_user_ids=emp_user_ids,
                dedup_key=f"leave_approved_{leave_id}",
            )
    except Exception as ne:
        log.warning(f"[leave] employee approved-notif failed: {ne}")

    out = await db.rahaza_leave_requests.find_one({"id": leave_id}, {"_id": 0})
    return serialize_doc(out)


@router.post("/leaves/{leave_id}/reject")
async def reject_leave(leave_id: str, request: Request):
    """Reject leave request."""
    user = await _require_leave_approver(request)
    db = get_db()
    body = await request.json()
    reason = body.get("reason") or "Tidak ada alasan"
    
    leave = await db.rahaza_leave_requests.find_one({"id": leave_id}, {"_id": 0})
    if not leave:
        raise HTTPException(404, "Leave request tidak ditemukan.")
    if leave.get("status") not in ("pending_approval", "pending_hr_approval"):
        raise HTTPException(400, f"Hanya leave Pending Approval yang bisa di-reject. Status: {leave.get('status')}")
    
    await db.rahaza_leave_requests.update_one(
        {"id": leave_id},
        {
            "$set": {
                "status": "rejected",
                "rejected_at": _now(),
                "rejected_by": user["id"],
                "rejected_by_name": user.get("name", ""),
                "rejected_reason": reason,
                "updated_at": _now(),
            }
        }
    )
    await log_activity(user["id"], user.get("name", ""), f"reject:{reason}", "rahaza.leave", leave_id)
    out = await db.rahaza_leave_requests.find_one({"id": leave_id}, {"_id": 0})
    return serialize_doc(out)


@router.post("/leaves/bulk-approve")
async def bulk_approve_leaves(request: Request):
    """Bulk approve all pending_approval leave requests (by list of IDs or all)."""
    user = await _require_leave_approver(request)
    db = get_db()
    body = await request.json()
    leave_ids = body.get("leave_ids")  # list or None (None = all pending)

    query = {"status": "pending_approval"}
    if leave_ids:
        query["id"] = {"$in": leave_ids}

    pending = await db.rahaza_leave_requests.find(query, {"_id": 0}).to_list(500)
    if not pending:
        return {"approved": 0, "skipped": 0, "message": "Tidak ada request pending untuk disetujui."}

    approved_count = 0
    # Batch prefetch leave types for all pending leaves
    lt_ids = list({lv.get("leave_type_id") for lv in pending if lv.get("leave_type_id")})
    lt_map = {}
    if lt_ids:
        async for d in db.rahaza_leave_types.find({"id": {"$in": lt_ids}}, {"_id": 0}):
            lt_map[d["id"]] = d
    for leave in pending:
        try:
            await db.rahaza_leave_requests.update_one(
                {"id": leave["id"]},
                {"$set": {
                    "status": "approved",
                    "approved_at": _now(),
                    "approved_by": user["id"],
                    "approved_by_name": user.get("name", ""),
                    "updated_at": _now(),
                }}
            )
            # Auto-create attendance records
            d_from = date.fromisoformat(leave["from_date"])
            d_to = date.fromisoformat(leave["to_date"])
            lt = lt_map.get(leave["leave_type_id"])
            current = d_from
            while current <= d_to:
                await db.rahaza_attendance_events.update_one(
                    {"employee_id": leave["employee_id"], "date": current.isoformat()},
                    {"$set": {"status": "cuti", "notes": f"Cuti: {lt.get('name') if lt else 'Leave'}", "leave_request_id": leave["id"], "updated_at": _now()},
                     "$setOnInsert": {"id": _uid(), "employee_id": leave["employee_id"], "date": current.isoformat(), "created_at": _now()}},
                    upsert=True,
                )
                current += timedelta(days=1)
            approved_count += 1
            await log_activity(user["id"], user.get("name", ""), "bulk_approve", "rahaza.leave", leave["id"])
        except Exception as e:
            log.error(f"bulk_approve: failed for {leave['id']}: {e}")

    return {"approved": approved_count, "skipped": len(pending) - approved_count,
            "message": f"{approved_count} request cuti berhasil disetujui."}


@router.delete("/leaves/{leave_id}")
async def delete_leave(leave_id: str, request: Request):
    """Delete draft/rejected leave request."""
    await require_auth(request)
    db = get_db()

    leave = await db.rahaza_leave_requests.find_one({"id": leave_id}, {"_id": 0})
    if not leave:
        raise HTTPException(404, "Leave request tidak ditemukan.")
    if leave.get("status") not in ("draft", "rejected"):
        raise HTTPException(400, "Hanya leave Draft/Rejected yang bisa dihapus.")

    await db.rahaza_leave_requests.delete_one({"id": leave_id})
    return {"status": "deleted"}


@router.post("/leaves/{leave_id}/cancel")
async def cancel_leave(leave_id: str, request: Request):
    """
    Batalkan leave yang sudah approved (future dates only).
    Saldo cuti dikembalikan. Attendance records (status=cuti) juga dihapus.
    """
    user = await require_auth(request)
    db   = get_db()
    body = await request.json()
    cancel_reason = (body.get("reason") or "Dibatalkan oleh karyawan").strip()

    leave = await db.rahaza_leave_requests.find_one({"id": leave_id}, {"_id": 0})
    if not leave:
        raise HTTPException(404, "Leave request tidak ditemukan.")
    if leave.get("status") != "approved":
        raise HTTPException(400, "Hanya leave Approved yang bisa dibatalkan.")

    # Cek apakah cuti sudah mulai (tanggal from_date sudah lewat)
    today = date.today()
    try:
        d_from = date.fromisoformat(leave["from_date"])
        if d_from < today:
            raise HTTPException(400,
                f"Tidak bisa membatalkan cuti yang sudah dimulai ({leave['from_date']}). "
                f"Hubungi HR untuk pembatalan manual.")
    except ValueError:
        logging.getLogger(__name__).debug("suppressed exception", exc_info=True)

    # Kembalikan saldo cuti
    try:
        from routes.rahaza_leave_balances import restore_balance
        await restore_balance(
            db,
            leave["employee_id"],
            leave["leave_type_id"],
            d_from.year,
            leave.get("duration_days", 1),
        )
    except Exception as e:
        log.warning(f"[cancel_leave] restore_balance failed: {e}")

    # Hapus attendance records yang dibuat saat approve
    try:
        d_to   = date.fromisoformat(leave["to_date"])
        cur    = d_from
        while cur <= d_to:
            await db.rahaza_attendance_events.delete_one({
                "employee_id": leave["employee_id"],
                "date":        cur.isoformat(),
                "leave_request_id": leave_id,
            })
            cur += timedelta(days=1)
    except Exception as e:
        log.warning(f"[cancel_leave] attendance cleanup failed: {e}")

    # Update status
    await db.rahaza_leave_requests.update_one(
        {"id": leave_id},
        {"$set": {
            "status":          "cancelled",
            "cancelled_at":    _now(),
            "cancelled_by":    user["id"],
            "cancelled_by_name": user.get("name", ""),
            "cancel_reason":   cancel_reason,
            "updated_at":      _now(),
        }}
    )
    await log_activity(user["id"], user.get("name", ""), "cancel", "rahaza.leave",
                       f"{leave_id} — {cancel_reason}")
    out = await db.rahaza_leave_requests.find_one({"id": leave_id}, {"_id": 0})
    return serialize_doc(out)
