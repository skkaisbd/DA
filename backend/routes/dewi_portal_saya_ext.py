"""
Session 15 — P2-13, P2-14, P2-15: Portal Saya Extension

P2-13: My Documents
- GET  /api/portal-saya/documents              — get my documents
- POST /api/portal-saya/documents              — upload/create document
- DELETE /api/portal-saya/documents/{doc_id}  — delete my document

P2-14: My Annual Review
- GET /api/portal-saya/annual-review           — get my review assignment & status

P2-15: Peer Feedback
- GET  /api/portal-saya/peer-feedback/received — feedback yang saya terima
- GET  /api/portal-saya/peer-feedback/given    — feedback yang saya beri
- POST /api/portal-saya/peer-feedback          — kirim feedback ke rekan
- GET  /api/portal-saya/peers                  — list rekan (untuk dropdown)
"""
import uuid
import logging
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Request, HTTPException, Query
from pydantic import BaseModel, Field
from database import get_db
from auth import require_auth

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/portal-saya", tags=["portal-saya-ext"])


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


async def _get_my_employee(db, user: dict):
    """Delegasi ke SSOT `utils.employee_identity.resolve_my_employee` (FASE 15).

    Versi lama mencocokkan `id`/`employee_code` user ke karyawan — pencocokan
    longgar yang bisa mengembalikan ORANG LAIN. SSOT hanya menerima tautan yang
    memang sengaja dibuat (employee_id / user_id / email).
    """
    from utils.employee_identity import resolve_my_employee
    return await resolve_my_employee(db, user)


# ═══════════════════════════════════════════════════════════════════════
#  P2-13: MY DOCUMENTS
# ═══════════════════════════════════════════════════════════════════════

class DocumentIn(BaseModel):
    title: str = Field(..., min_length=1)
    doc_type: str = Field(default="other", description="ktp, ijazah, sertifikat, kontrak, other")
    description: Optional[str] = None
    file_url: Optional[str] = None
    file_name: Optional[str] = None
    expiry_date: Optional[str] = None


@router.get("/documents")
async def get_my_documents(request: Request):
    """P2-13: Get documents for the current logged-in user."""
    user = await require_auth(request)
    db = get_db()

    emp = await _get_my_employee(db, user)
    emp_id = emp.get("id") or emp.get("employee_code") if emp else user.get("id")

    docs = await db.employee_documents.find(
        {"employee_id": emp_id},
        {"_id": 0}
    ).sort("created_at", -1).to_list(200)

    # Also get standard HR documents issued by HR (contracts, letters)
    hr_docs = await db.hr_issued_documents.find(
        {"employee_id": emp_id},
        {"_id": 0}
    ).sort("issued_at", -1).to_list(50)

    return ok(
        data={"my_documents": serialize(docs), "hr_issued": serialize(hr_docs)},
        meta={"total": len(docs) + len(hr_docs)}
    )


@router.post("/documents")
async def create_my_document(payload: DocumentIn, request: Request):
    """P2-13: Upload/create a new personal document."""
    user = await require_auth(request)
    db = get_db()

    emp = await _get_my_employee(db, user)
    emp_id = emp.get("id") or emp.get("employee_code") if emp else user.get("id")
    emp_name = emp.get("name") if emp else user.get("name", "")

    doc = {
        "id": str(uuid.uuid4()),
        "employee_id": emp_id,
        "employee_name": emp_name,
        "title": payload.title,
        "doc_type": payload.doc_type,
        "description": payload.description,
        "file_url": payload.file_url,
        "file_name": payload.file_name,
        "expiry_date": payload.expiry_date,
        "created_at": _now().isoformat(),
        "updated_at": _now().isoformat(),
    }
    await db.employee_documents.insert_one(doc)
    return ok(data=serialize(doc))


@router.delete("/documents/{doc_id}")
async def delete_my_document(doc_id: str, request: Request):
    """P2-13: Delete own document."""
    user = await require_auth(request)
    db = get_db()

    emp = await _get_my_employee(db, user)
    emp_id = emp.get("id") or emp.get("employee_code") if emp else user.get("id")

    doc = await db.employee_documents.find_one({"id": doc_id})
    if not doc:
        raise HTTPException(404, "Dokumen tidak ditemukan")
    if doc.get("employee_id") != emp_id and user.get("role") not in ("superadmin", "admin"):
        raise HTTPException(403, "Tidak boleh hapus dokumen orang lain")

    await db.employee_documents.delete_one({"id": doc_id})
    return ok(data={"deleted": True})


# ═══════════════════════════════════════════════════════════════════════
#  P2-14: MY ANNUAL REVIEW
# ═══════════════════════════════════════════════════════════════════════

@router.get("/annual-review")
async def get_my_annual_review(request: Request):
    """
    P2-14: Get current user's performance review assignments and review status.
    """
    user = await require_auth(request)
    db = get_db()

    emp = await _get_my_employee(db, user)
    emp_id = emp.get("id") or emp.get("employee_code") if emp else user.get("id")

    if not emp_id:
        return ok(data={"assignments": [], "reviews": [], "cycles": []})

    # Get my assignments (I am the reviewee or reviewer)
    assignments = await db.hris_assignments.find(
        {"$or": [{"employee_id": emp_id}, {"reviewer_id": emp_id}]},
        {"_id": 0}
    ).sort("created_at", -1).to_list(50)

    # Get my review submissions
    reviews = await db.hris_reviews.find(
        {"employee_id": emp_id},
        {"_id": 0}
    ).sort("submitted_at", -1).to_list(20)

    # Get active cycles
    cycles = await db.hris_cycles.find(
        {"status": {"$in": ["active", "in_progress"]}},
        {"_id": 0}
    ).sort("start_date", -1).to_list(5)

    # Get my KPI assignments
    kpis = await db.hris_kpi_assignments.find(
        {"employee_id": emp_id},
        {"_id": 0}
    ).to_list(20)

    return ok(data={
        "employee": serialize(emp) if emp else {},
        "assignments": serialize(assignments),
        "reviews": serialize(reviews),
        "cycles": serialize(cycles),
        "kpis": serialize(kpis),
    })


# ═══════════════════════════════════════════════════════════════════════
#  P2-15: PEER FEEDBACK
# ═══════════════════════════════════════════════════════════════════════

class PeerFeedbackIn(BaseModel):
    to_employee_id: str = Field(..., description="Employee ID penerima feedback")
    to_employee_name: Optional[str] = None
    rating: int = Field(..., ge=1, le=5, description="Rating 1-5")
    category: str = Field(default="general", description="teamwork, communication, quality, leadership, general")
    message: str = Field(..., min_length=10, description="Pesan feedback")
    is_anonymous: bool = Field(default=False)


@router.get("/peers")
async def get_peers_for_feedback(request: Request):
    """List active employees (excluding self) for peer feedback dropdown."""
    user = await require_auth(request)
    db = get_db()

    emp = await _get_my_employee(db, user)
    my_id = emp.get("id") or emp.get("employee_code") if emp else user.get("id")

    emps = await db.rahaza_employees.find(
        {"employment_status": "active"},
        {"_id": 0, "id": 1, "employee_code": 1, "name": 1, "department": 1, "job_title": 1}
    ).sort("name", 1).to_list(200)

    # Exclude self
    peers = [e for e in emps if e.get("id") != my_id and e.get("employee_code") != my_id]
    return ok(data=serialize(peers))


@router.get("/peer-feedback/received")
async def get_received_feedback(request: Request):
    """P2-15: Get peer feedback received by current user."""
    user = await require_auth(request)
    db = get_db()

    emp = await _get_my_employee(db, user)
    emp_id = emp.get("id") or emp.get("employee_code") if emp else user.get("id")

    feedbacks = await db.peer_feedbacks.find(
        {"to_employee_id": emp_id},
        {"_id": 0}
    ).sort("created_at", -1).to_list(100)

    # Hide sender name for anonymous feedbacks
    clean = []
    for f in feedbacks:
        if f.get("is_anonymous"):
            f["from_employee_name"] = "Anonim"
            f["from_employee_id"] = None
        clean.append(f)

    avg_rating = sum(f.get("rating", 0) for f in clean) / len(clean) if clean else 0
    return ok(
        data=serialize(clean),
        meta={"total": len(clean), "avg_rating": round(avg_rating, 1)}
    )


@router.get("/peer-feedback/given")
async def get_given_feedback(request: Request):
    """P2-15: Get feedback given by current user."""
    user = await require_auth(request)
    db = get_db()

    emp = await _get_my_employee(db, user)
    emp_id = emp.get("id") or emp.get("employee_code") if emp else user.get("id")

    feedbacks = await db.peer_feedbacks.find(
        {"from_employee_id": emp_id},
        {"_id": 0}
    ).sort("created_at", -1).to_list(100)

    return ok(data=serialize(feedbacks), meta={"total": len(feedbacks)})


# ═══════════════════════════════════════════════════════════════════════
#  ME/* ENDPOINTS — Digunakan oleh PortalSayaCuti.jsx & PortalSayaPayslip.jsx
# ═══════════════════════════════════════════════════════════════════════

@router.get("/me/employee")
async def get_my_employee_record(request: Request):
    """Get employee record linked to the current logged-in user."""
    user = await require_auth(request)
    db = get_db()
    emp = await _get_my_employee(db, user)
    if not emp:
        raise HTTPException(404, "Akun belum terhubung ke data karyawan. Hubungi HR Admin.")
    return serialize(emp)


@router.get("/me/leaves")
async def get_my_leaves(
    request: Request,
    limit: int = Query(50, ge=1, le=500),
    status: str = "",
):
    """Get leave requests for the current logged-in employee."""
    user = await require_auth(request)
    db = get_db()
    emp = await _get_my_employee(db, user)
    if not emp:
        raise HTTPException(404, "Akun belum terhubung ke data karyawan.")
    emp_id = emp.get("id") or emp.get("employee_code")

    q = {"employee_id": emp_id}
    if status:
        q["status"] = status

    items = await db.rahaza_leave_requests.find(q, {"_id": 0})\
        .sort("created_at", -1).limit(limit).to_list(limit)

    return {"items": serialize(items), "total": len(items)}


@router.get("/me/leave-balance")
async def get_my_leave_balance(request: Request):
    """Get leave balance for the current logged-in employee."""
    user = await require_auth(request)
    db = get_db()
    emp = await _get_my_employee(db, user)
    if not emp:
        raise HTTPException(404, "Akun belum terhubung ke data karyawan.")
    emp_id = emp.get("id") or emp.get("employee_code")

    # Get leave types
    leave_types = await db.rahaza_leave_types.find({}, {"_id": 0}).to_list(50)
    type_map = {lt["id"]: lt for lt in leave_types}

    # Get leave balances for this employee
    balances = await db.rahaza_leave_balances.find(
        {"employee_id": emp_id}, {"_id": 0}
    ).to_list(50)

    # Enrich with leave type info
    enriched = []
    for b in balances:
        lt = type_map.get(b.get("leave_type_id"), {})
        enriched.append({
            **b,
            "leave_type_name": lt.get("name", b.get("leave_type_id", "")),
            "leave_type_color": lt.get("color", "#6366f1"),
        })

    return {"balances": serialize(enriched), "employee_id": emp_id}


@router.get("/me/payslips")
async def get_my_payslips(
    request: Request,
    limit: int = Query(12, ge=1, le=500),
):
    """Get payslips for the current logged-in employee."""
    user = await require_auth(request)
    db = get_db()
    emp = await _get_my_employee(db, user)
    if not emp:
        raise HTTPException(409, "Akun belum terhubung ke data karyawan.")
    emp_id = emp.get("id") or emp.get("employee_code")

    # Find payslips from rahaza_payroll_payslips collection
    payslips = await db.rahaza_payslips.find(
        {"employee_id": emp_id}, {"_id": 0}
    ).sort("created_at", -1).limit(limit).to_list(limit)

    return {"payslips": serialize(payslips), "total": len(payslips)}


@router.post("/peer-feedback")
async def submit_peer_feedback(payload: PeerFeedbackIn, request: Request):
    """P2-15: Submit peer feedback."""
    user = await require_auth(request)
    db = get_db()

    emp = await _get_my_employee(db, user)
    from_id   = emp.get("id") or emp.get("employee_code") if emp else user.get("id")
    from_name = emp.get("name") if emp else user.get("name", "")

    # Prevent self-feedback
    if payload.to_employee_id == from_id:
        raise HTTPException(400, "Tidak bisa memberikan feedback ke diri sendiri")

    # Verify receiver exists
    to_emp = await db.rahaza_employees.find_one(
        {"$or": [{"id": payload.to_employee_id}, {"employee_code": payload.to_employee_id}]}
    )
    if not to_emp:
        raise HTTPException(404, "Karyawan penerima tidak ditemukan")

    feedback = {
        "id": str(uuid.uuid4()),
        "from_employee_id": from_id,
        "from_employee_name": from_name if not payload.is_anonymous else "Anonim",
        "to_employee_id": payload.to_employee_id,
        "to_employee_name": to_emp.get("name"),
        "rating": payload.rating,
        "category": payload.category,
        "message": payload.message,
        "is_anonymous": payload.is_anonymous,
        "created_at": _now().isoformat(),
    }
    await db.peer_feedbacks.insert_one(feedback)

    # Trigger notification (simple in-app) → unified SSOT (type='dewi')
    from utils.notif_unified import notif_insert as _notif_insert
    await _notif_insert(
        db,
        type='dewi',
        body=f"Kamu mendapat feedback peer baru ({'anonim' if payload.is_anonymous else from_name})",
        subtype='peer_feedback',
        title='Feedback Baru Diterima',
        user_id=payload.to_employee_id,
        channel='in_app',
    )

    return ok(data=serialize(feedback))
