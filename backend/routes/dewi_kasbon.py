"""
CV. Dewi Aditya ERP — Kasbon & Pinjaman Karyawan (Phase 12)
Collection: dewi_kasbon_requests

Status Flow:
  submitted → hr_approved | hr_rejected → disbursed (aktif) → paid_off
  
Types:
  kasbon  : Gaji dimuka, lunas 1x potongan gaji
  pinjaman: Cicilan bulanan, auto-potong gaji setiap periode

API:
  POST   /api/dewi/kasbon/requests            — Ajukan kasbon/pinjaman (staff/admin)
  GET    /api/dewi/kasbon/requests            — List semua (HR/Finance) atau milik sendiri
  GET    /api/dewi/kasbon/my-requests         — List milik sendiri (staff)
  GET    /api/dewi/kasbon/requests/{id}       — Detail
  PATCH  /api/dewi/kasbon/requests/{id}/hr-review   — HR approve/reject
  PATCH  /api/dewi/kasbon/requests/{id}/disburse    — Finance cairkan
  POST   /api/dewi/kasbon/requests/{id}/repay       — Catat pembayaran manual
  POST   /api/dewi/kasbon/requests/{id}/cancel      — Batalkan (staff, status submitted)
  GET    /api/dewi/kasbon/stats               — Dashboard stats
  GET    /api/dewi/kasbon/employee/{id}/deductions  — Deductions untuk payroll
  POST   /api/dewi/kasbon/apply-payroll-deductions  — Batch record payroll deductions
"""
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from motor.motor_asyncio import AsyncIOMotorDatabase
from database import get_db
from core.doc_number_policy import issue_number  # FASE G — satu pintu penomoran
from auth import require_auth
from datetime import datetime, timezone, date
from typing import Optional
import logging
import uuid
import math

router = APIRouter(prefix="/api/dewi/kasbon", tags=["Kasbon"])

# F13 — modul ini menyentuh UANG (pencairan kasbon + jurnalnya). Tanpa logger,
# satu-satunya jejak kegagalan posting adalah nilai balik yang sering tidak
# diperiksa pemanggilnya.
_log = logging.getLogger(__name__)


async def _post_kasbon_gl(db, event_type: str, source_ref: str, memo: str, amount: float, user: dict):
    """Fire GL posting for kasbon events. Graceful — never raises."""
    try:
        from routes.rahaza_posting import _create_posted_je
        from routes.rahaza_posting_profiles import get_mapping
        mapping = await get_mapping(db, event_type)
        if not mapping:
            return {"ok": False, "error": f"Posting profile '{event_type}' tidak ditemukan."}
        if event_type == "employee_loan_disbursement":
            lines = [
                {"account_code": mapping.get("debit_employee_loan_receivable") or mapping.get("debit_loan_receivable"),
                 "debit": amount, "credit": 0, "description": memo},
                {"account_code": mapping.get("credit_cash"),
                 "debit": 0, "credit": amount, "description": memo},
            ]
        elif event_type == "employee_loan_repayment_payroll":
            lines = [
                {"account_code": mapping.get("debit_salary_payable"),
                 "debit": amount, "credit": 0, "description": memo},
                {"account_code": mapping.get("credit_employee_loan_receivable") or mapping.get("credit_loan_receivable"),
                 "debit": 0, "credit": amount, "description": memo},
            ]
        elif event_type == "employee_loan_repayment_manual":
            lines = [
                {"account_code": mapping.get("debit_bank"),
                 "debit": amount, "credit": 0, "description": memo},
                {"account_code": mapping.get("credit_employee_loan_receivable") or mapping.get("credit_loan_receivable"),
                 "debit": 0, "credit": amount, "description": memo},
            ]
        else:
            return {"ok": False, "error": f"Unknown kasbon event_type: {event_type}"}
        je_date = date.today()
        return await _create_posted_je(db, je_date, memo, event_type, source_ref, lines, user)
    except Exception as exc:
        # F13 — DULU kegagalan posting jurnal kasbon hanya dikembalikan sebagai
        # `{"ok": False}` TANPA satu baris log. Pemanggil di beberapa jalur hanya
        # membaca hasilnya untuk ditampilkan, jadi kasbon bisa CAIR (uang keluar)
        # sementara jurnalnya tidak pernah terbentuk — dan tidak ada jejak untuk
        # menemukannya lagi. Tetap non-blocking supaya pencairan tidak menggantung,
        # tapi kini selalu meninggalkan bukti.
        _log.exception(
            "[kasbon] posting jurnal GAGAL event=%s source_ref=%s — kasbon "
            "berpotensi tercatat tanpa jurnal, perlu penjurnalan manual",
            event_type, source_ref)
        return {"ok": False, "error": str(exc)}


def _now():
    return datetime.now(timezone.utc)


def _uid():
    return str(uuid.uuid4())[:12]


def _sid():
    return str(uuid.uuid4())[:8]


def _ser(doc):
    if doc is None:
        return None
    doc = dict(doc)
    doc.pop("_id", None)
    for k, v in doc.items():
        if isinstance(v, datetime):
            doc[k] = v.isoformat()
    return doc


# ─── Request Submit ───────────────────────────────────────────────────────────
@router.post("/requests")
async def submit_kasbon_request(
    request: Request,
    db: AsyncIOMotorDatabase = Depends(get_db),
    user=Depends(require_auth),
):
    body = await request.json()

    req_type = body.get("type", "kasbon")
    if req_type not in ("kasbon", "pinjaman"):
        raise HTTPException(400, "type harus 'kasbon' atau 'pinjaman'")

    amount = float(body.get("amount", 0))
    if amount <= 0:
        raise HTTPException(400, "Jumlah harus lebih dari 0")

    installment_count = int(body.get("installment_count", 1))
    if req_type == "kasbon":
        installment_count = 1

    if installment_count < 1:
        raise HTTPException(400, "Jumlah cicilan minimal 1")

    installment_amount = math.ceil(amount / installment_count)

    # Get employee info
    employee_id = body.get("employee_id") or user.get("employee_id") or user.get("id")
    emp = await db.rahaza_employees.find_one(
        {"$or": [{"id": employee_id}, {"employee_id": employee_id}]}, {"_id": 0}
    )
    if not emp:
        # Try lookup by email
        emp = await db.rahaza_employees.find_one({"email": user.get("email")}, {"_id": 0})

    emp_name = (emp or {}).get("name") or body.get("employee_name") or user.get("name", "")
    emp_code = (emp or {}).get("employee_code") or (emp or {}).get("code") or ""
    department = (emp or {}).get("department") or body.get("department") or ""
    emp_email = (emp or {}).get("email") or user.get("email", "")
    actual_emp_id = (emp or {}).get("id") or (emp or {}).get("employee_id") or employee_id

    # ── FASE G (sesi #18) — KEBIJAKAN PENOMORAN DITEGAKKAN ────────────────────
    # Sebelum ini nomor SELALU dibuat otomatis (`KSB-00001`/`PIN-00001`) sehingga
    # setelan "Otomatis/Manual" di Administrasi Sistem → Penomoran Dokumen tidak
    # berpengaruh apa pun untuk dokumen ini — setelan yang tidak ditegakkan adalah
    # setelan yang BERBOHONG. Sekarang satu pintu `issue_number`:
    #   · mode OTOMATIS → nomor dibuat mengikuti FORMAT yang disetel owner, dan
    #     nomor ketikan DITOLAK (bukan diabaikan diam-diam);
    #   · mode MANUAL  → nomor wajib diisi DAN wajib mengikuti pola formatnya.
    # Kasbon & Pinjaman memakai KUNCI BERBEDA walau satu koleksi, supaya memindah
    # kebijakan kasbon tidak ikut memaksa pinjaman.
    req_number = await issue_number(
        db,
        "dewi_kasbon_requests.request_number" if req_type == "kasbon"
        else "dewi_kasbon_requests.request_number_pinjaman",
        requested=(body.get("request_number") or ""))

    # Documents: [{name, data, mime_type}] — base64 encoded
    documents = body.get("documents") or []

    doc = {
        "id": _uid(),
        "request_number": req_number,
        "employee_id": actual_emp_id,
        "employee_name": emp_name,
        "employee_code": emp_code,
        "employee_email": emp_email,
        "department": department,
        "type": req_type,
        "type_label": "Kasbon" if req_type == "kasbon" else "Pinjaman",
        "amount": amount,
        "purpose": body.get("purpose", ""),
        "notes": body.get("notes", ""),
        "documents": documents,
        "installment_count": installment_count,
        "installment_amount": installment_amount,
        # Status
        "status": "submitted",
        # HR review
        "hr_reviewed_by": None,
        "hr_reviewed_at": None,
        "hr_notes": None,
        # Finance disbursal
        "disbursed_by": None,
        "disbursed_at": None,
        "disbursement_date": None,
        "deduction_start_period": None,
        "finance_notes": None,
        # Repayment tracking
        "paid_amount": 0.0,
        "outstanding_balance": amount,
        "repayments": [],
        # Meta
        "submitted_by": user.get("email", ""),
        "submitted_by_name": user.get("name", ""),
        "created_at": _now().isoformat(),
        "updated_at": _now().isoformat(),
    }

    await db.dewi_kasbon_requests.insert_one(doc)
    doc.pop("_id", None)
    return {"ok": True, "request": doc}


# ─── List ─────────────────────────────────────────────────────────────────────
@router.get("/requests")
async def list_kasbon_requests(
    db: AsyncIOMotorDatabase = Depends(get_db),
    user=Depends(require_auth),
    status: Optional[str] = None,
    type: Optional[str] = None,
    employee_id: Optional[str] = None,
    department: Optional[str] = None,
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=500),
):
    filt = {}
    if status:
        filt["status"] = status
    if type:
        filt["type"] = type
    if employee_id:
        filt["employee_id"] = employee_id
    if department:
        filt["department"] = department

    total = await db.dewi_kasbon_requests.count_documents(filt)
    docs = (
        await db.dewi_kasbon_requests.find(filt, {"_id": 0, "documents": 0})
        .sort("created_at", -1)
        .skip((page - 1) * limit)
        .to_list(limit)
    )
    return {"ok": True, "total": total, "requests": [_ser(d) for d in docs]}


# ─── My Requests (Staff) ──────────────────────────────────────────────────────
@router.get("/my-requests")
async def my_kasbon_requests(
    db: AsyncIOMotorDatabase = Depends(get_db),
    user=Depends(require_auth),
    status: Optional[str] = None,
):
    emp = await db.rahaza_employees.find_one({"email": user.get("email")}, {"_id": 0})
    emp_id = (emp or {}).get("id") or (emp or {}).get("employee_id") or user.get("employee_id")

    filt = {}
    if emp_id:
        filt["employee_id"] = emp_id
    else:
        filt["submitted_by"] = user.get("email", "")

    if status:
        filt["status"] = status

    docs = (
        await db.dewi_kasbon_requests.find(filt, {"_id": 0, "documents": 0})
        .sort("created_at", -1)
        .to_list(100)
    )
    return {"ok": True, "requests": [_ser(d) for d in docs]}


# ─── Detail ───────────────────────────────────────────────────────────────────
@router.get("/requests/{req_id}")
async def get_kasbon_detail(
    req_id: str,
    db: AsyncIOMotorDatabase = Depends(get_db),
    user=Depends(require_auth),
):
    doc = await db.dewi_kasbon_requests.find_one({"id": req_id}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Kasbon tidak ditemukan")
    return {"ok": True, "request": _ser(doc)}


# ─── HR Review ────────────────────────────────────────────────────────────────
@router.patch("/requests/{req_id}/hr-review")
async def hr_review_kasbon(
    req_id: str,
    request: Request,
    db: AsyncIOMotorDatabase = Depends(get_db),
    user=Depends(require_auth),
):
    body = await request.json()
    action = body.get("action")  # "approve" | "reject"
    if action not in ("approve", "reject"):
        raise HTTPException(400, "action harus 'approve' atau 'reject'")

    doc = await db.dewi_kasbon_requests.find_one({"id": req_id}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Kasbon tidak ditemukan")
    if doc.get("status") != "submitted":
        raise HTTPException(400, f"Status saat ini '{doc.get('status')}', hanya bisa review saat 'submitted'")

    new_status = "hr_approved" if action == "approve" else "hr_rejected"
    upd = {
        "status": new_status,
        "hr_reviewed_by": user.get("name", user.get("email", "")),
        "hr_reviewed_at": _now().isoformat(),
        "hr_notes": body.get("notes", ""),
        "updated_at": _now().isoformat(),
    }
    await db.dewi_kasbon_requests.update_one({"id": req_id}, {"$set": upd})
    updated = await db.dewi_kasbon_requests.find_one({"id": req_id}, {"_id": 0})
    return {"ok": True, "request": _ser(updated)}


# ─── Finance Disburse ─────────────────────────────────────────────────────────
@router.patch("/requests/{req_id}/disburse")
async def finance_disburse(
    req_id: str,
    request: Request,
    db: AsyncIOMotorDatabase = Depends(get_db),
    user=Depends(require_auth),
):
    body = await request.json()

    doc = await db.dewi_kasbon_requests.find_one({"id": req_id}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Kasbon tidak ditemukan")
    if doc.get("status") != "hr_approved":
        raise HTTPException(400, f"Status '{doc.get('status')}', harus 'hr_approved' untuk dicairkan")

    disbursement_date = body.get("disbursement_date") or _now().strftime("%Y-%m-%d")
    deduction_start_period = body.get("deduction_start_period") or _now().strftime("%Y-%m")

    upd = {
        "status": "disbursed",
        "disbursed_by": user.get("name", user.get("email", "")),
        "disbursed_at": _now().isoformat(),
        "disbursement_date": disbursement_date,
        "deduction_start_period": deduction_start_period,
        "finance_notes": body.get("finance_notes", ""),
        "updated_at": _now().isoformat(),
    }
    await db.dewi_kasbon_requests.update_one({"id": req_id}, {"$set": upd})
    updated = await db.dewi_kasbon_requests.find_one({"id": req_id}, {"_id": 0})

    # Auto-GL: Dr Kasbon Karyawan / Cr Bank
    amount_val = float(doc.get("amount", 0))
    emp_name_val = doc.get("employee_name", "")
    gl_result = await _post_kasbon_gl(
        db, "employee_loan_disbursement",
        f"kasbon-disburse-{req_id}",
        f"Kasbon Cair — {emp_name_val} — {doc.get('request_number','')}",
        amount_val, user,
    )
    return {"ok": True, "request": _ser(updated), "gl": gl_result}


# ─── Record Repayment ─────────────────────────────────────────────────────────
@router.post("/requests/{req_id}/repay")
async def record_repayment(
    req_id: str,
    request: Request,
    db: AsyncIOMotorDatabase = Depends(get_db),
    user=Depends(require_auth),
):
    body = await request.json()
    amount = float(body.get("amount", 0))
    if amount <= 0:
        raise HTTPException(400, "Jumlah pembayaran harus > 0")

    doc = await db.dewi_kasbon_requests.find_one({"id": req_id}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Kasbon tidak ditemukan")
    if doc.get("status") not in ("disbursed", "active"):
        raise HTTPException(400, "Kasbon harus berstatus aktif untuk dicatat pembayarannya")

    outstanding = float(doc.get("outstanding_balance", 0))
    actual = min(amount, outstanding)
    new_paid = float(doc.get("paid_amount", 0)) + actual
    new_outstanding = outstanding - actual
    new_status = "paid_off" if new_outstanding <= 0.01 else doc.get("status")

    repayment_entry = {
        "id": _sid(),
        "amount": round(actual, 2),
        "date": body.get("date") or _now().strftime("%Y-%m-%d"),
        "method": body.get("method", "manual"),
        "period": body.get("period", ""),
        "notes": body.get("notes", ""),
        "by": user.get("name", user.get("email", "")),
        "created_at": _now().isoformat(),
    }

    upd = {
        "paid_amount": round(new_paid, 2),
        "outstanding_balance": round(new_outstanding, 2),
        "status": new_status,
        "updated_at": _now().isoformat(),
    }
    await db.dewi_kasbon_requests.update_one(
        {"id": req_id},
        {"$set": upd, "$push": {"repayments": repayment_entry}},
    )
    updated = await db.dewi_kasbon_requests.find_one({"id": req_id}, {"_id": 0})

    # Auto-GL posting berdasarkan metode pembayaran
    method = body.get("method", "manual")
    event_type_gl = (
        "employee_loan_repayment_payroll" if method == "payroll_deduction"
        else "employee_loan_repayment_manual"
    )
    emp_name_rep = doc.get("employee_name", "")
    gl_result = await _post_kasbon_gl(
        db, event_type_gl,
        f"kasbon-repay-{repayment_entry['id']}",
        f"Angsuran Kasbon — {emp_name_rep} — {doc.get('request_number','')} ({method})",
        round(actual, 2), user,
    )
    return {"ok": True, "request": _ser(updated), "repayment": repayment_entry, "gl": gl_result}


# ─── Cancel ───────────────────────────────────────────────────────────────────
@router.post("/requests/{req_id}/cancel")
async def cancel_kasbon(
    req_id: str,
    request: Request,
    db: AsyncIOMotorDatabase = Depends(get_db),
    user=Depends(require_auth),
):
    body = await request.json()
    doc = await db.dewi_kasbon_requests.find_one({"id": req_id}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Kasbon tidak ditemukan")
    if doc.get("status") not in ("submitted",):
        raise HTTPException(400, "Hanya bisa batalkan saat status 'submitted'")

    await db.dewi_kasbon_requests.update_one(
        {"id": req_id},
        {"$set": {
            "status": "cancelled",
            "cancel_reason": body.get("reason", ""),
            "cancelled_by": user.get("email", ""),
            "updated_at": _now().isoformat(),
        }},
    )
    return {"ok": True}


# ─── Stats Dashboard ──────────────────────────────────────────────────────────
@router.get("/stats")
async def kasbon_stats(
    db: AsyncIOMotorDatabase = Depends(get_db),
    user=Depends(require_auth),
):
    all_docs = await db.dewi_kasbon_requests.find({}, {"_id": 0, "documents": 0}).to_list(1000)

    pending_hr = [d for d in all_docs if d.get("status") == "submitted"]
    pending_finance = [d for d in all_docs if d.get("status") == "hr_approved"]
    active = [d for d in all_docs if d.get("status") == "disbursed"]
    paid_off = [d for d in all_docs if d.get("status") == "paid_off"]

    total_outstanding = sum(float(d.get("outstanding_balance", 0)) for d in active)
    total_disbursed_all = sum(float(d.get("amount", 0)) for d in all_docs if d.get("status") in ("disbursed", "paid_off"))

    # This month (robust: created_at bisa str ISO ATAU datetime — data seed lama menyimpan datetime)
    now_ym = _now().strftime("%Y-%m")

    def _ym(v):
        if isinstance(v, datetime):
            return v.strftime("%Y-%m")
        return str(v or "")[:7]

    this_month = [d for d in all_docs if _ym(d.get("created_at")) == now_ym]

    return {
        "ok": True,
        "stats": {
            "pending_hr": len(pending_hr),
            "pending_finance": len(pending_finance),
            "active_count": len(active),
            "paid_off_count": len(paid_off),
            "total_outstanding": round(total_outstanding, 2),
            "total_disbursed_all": round(total_disbursed_all, 2),
            "this_month_requests": len(this_month),
            "this_month_amount": sum(float(d.get("amount", 0)) for d in this_month),
        },
        "active_list": [_ser(d) for d in active],
        "pending_hr_list": [_ser(d) for d in pending_hr],
    }


# ─── Payroll Deductions (per employee per period) ─────────────────────────────
@router.get("/employee/{emp_id}/deductions")
async def get_employee_deductions(
    emp_id: str,
    period: str = Query(..., description="Format YYYY-MM"),
    db: AsyncIOMotorDatabase = Depends(get_db),
    user=Depends(require_auth),
):
    """Ambil potongan kasbon/pinjaman untuk karyawan pada periode tertentu."""
    active_ks = await db.dewi_kasbon_requests.find({
        "employee_id": emp_id,
        "status": "disbursed",
        "deduction_start_period": {"$lte": period},
    }, {"_id": 0, "documents": 0}).to_list(50)

    deductions = []
    for ks in active_ks:
        outstanding = float(ks.get("outstanding_balance", 0))
        if outstanding <= 0:
            continue
        if ks.get("type") == "kasbon":
            amt = outstanding
        else:
            amt = min(float(ks.get("installment_amount", 0)), outstanding)
        if amt > 0:
            deductions.append({
                "kasbon_id": ks["id"],
                "request_number": ks.get("request_number", ""),
                "type": ks.get("type"),
                "type_label": ks.get("type_label", ""),
                "amount": round(amt, 2),
                "outstanding_balance": round(outstanding, 2),
                "label": f"Potongan {ks.get('type_label','Kasbon')} {ks.get('request_number','')}",
            })

    return {
        "ok": True,
        "employee_id": emp_id,
        "period": period,
        "deductions": deductions,
        "total_deduction": sum(d["amount"] for d in deductions),
    }


# ─── Apply Payroll Deductions (batch — called after payroll finalized) ─────────
@router.post("/apply-payroll-deductions")
async def apply_payroll_deductions(
    request: Request,
    db: AsyncIOMotorDatabase = Depends(get_db),
    user=Depends(require_auth),
):
    """
    Batch record payroll deductions for a period.
    Body: {period: 'YYYY-MM', deductions: [{kasbon_id, amount, employee_id}]}
    """
    body = await request.json()
    period = body.get("period")
    deductions = body.get("deductions", [])

    if not period:
        raise HTTPException(400, "period diperlukan (YYYY-MM)")

    results = []
    for ded in deductions:
        kasbon_id = ded.get("kasbon_id")
        amount = float(ded.get("amount", 0))
        if not kasbon_id or amount <= 0:
            continue

        doc = await db.dewi_kasbon_requests.find_one({"id": kasbon_id}, {"_id": 0})
        if not doc or doc.get("status") not in ("disbursed",):
            continue

        # Check not already recorded for this period
        already = any(
            r.get("period") == period and r.get("method") == "payroll_deduction"
            for r in (doc.get("repayments") or [])
        )
        if already:
            results.append({"kasbon_id": kasbon_id, "skipped": True, "reason": "Sudah dicatat periode ini"})
            continue

        outstanding = float(doc.get("outstanding_balance", 0))
        actual = min(amount, outstanding)
        new_paid = float(doc.get("paid_amount", 0)) + actual
        new_outstanding = outstanding - actual
        new_status = "paid_off" if new_outstanding <= 0.01 else "disbursed"

        repayment_entry = {
            "id": _sid(),
            "amount": round(actual, 2),
            "date": _now().strftime("%Y-%m-%d"),
            "method": "payroll_deduction",
            "period": period,
            "notes": f"Auto-potong gaji periode {period}",
            "by": user.get("name", "Payroll System"),
            "created_at": _now().isoformat(),
        }

        await db.dewi_kasbon_requests.update_one(
            {"id": kasbon_id},
            {"$set": {
                "paid_amount": round(new_paid, 2),
                "outstanding_balance": round(new_outstanding, 2),
                "status": new_status,
                "updated_at": _now().isoformat(),
            }, "$push": {"repayments": repayment_entry}},
        )
        # Auto-GL: Dr Hutang Gaji / Cr Kasbon Karyawan
        gl_result = await _post_kasbon_gl(
            db, "employee_loan_repayment_payroll",
            f"kasbon-payroll-{kasbon_id}-{period}",
            f"Auto-potong gaji {period} — Kasbon {kasbon_id}",
            actual, user,
        )
        results.append({
            "kasbon_id": kasbon_id,
            "amount_deducted": actual,
            "new_outstanding": new_outstanding,
            "new_status": new_status,
            "gl": gl_result,
        })

    return {"ok": True, "period": period, "processed": len(results), "results": results}


# ─── Seed Demo Data ───────────────────────────────────────────────────────────
@router.post("/seed")
async def seed_demo(
    db: AsyncIOMotorDatabase = Depends(get_db),
    user=Depends(require_auth),
):
    existing = await db.dewi_kasbon_requests.count_documents({})
    if existing > 0:
        return {"ok": True, "message": "Data demo sudah ada"}

    emps = await db.rahaza_employees.find({"active": True}, {"_id": 0}).limit(5).to_list(5)
    if not emps:
        emps = await db.rahaza_employees.find({}, {"_id": 0}).limit(5).to_list(5)

    samples = [
        {"type": "kasbon", "amount": 1500000, "purpose": "Biaya pengobatan keluarga", "status": "submitted", "installment_count": 1},
        {"type": "pinjaman", "amount": 5000000, "purpose": "Renovasi rumah", "status": "hr_approved", "installment_count": 5},
        {"type": "kasbon", "amount": 800000, "purpose": "Keperluan pendidikan anak", "status": "disbursed", "installment_count": 1},
        {"type": "pinjaman", "amount": 3000000, "purpose": "Modal usaha sampingan", "status": "disbursed", "installment_count": 3},
        {"type": "kasbon", "amount": 2000000, "purpose": "Biaya pernikahan", "status": "paid_off", "installment_count": 1},
    ]

    for i, s in enumerate(samples):
        emp = emps[i % len(emps)] if emps else {}
        emp_id = emp.get("id") or emp.get("employee_id") or f"EMP-{i+1:03d}"
        emp_name = emp.get("name") or emp.get("full_name") or f"Karyawan {i+1}"
        amount = s["amount"]
        installment_count = s["installment_count"]
        installment_amount = math.ceil(amount / installment_count)
        paid = amount if s["status"] == "paid_off" else (installment_amount if s["status"] == "disbursed" else 0)
        outstanding = amount - paid

        prefix = "KSB" if s["type"] == "kasbon" else "PIN"
        req_number = f"{prefix}-{(i+1):05d}"

        doc = {
            "id": _uid(),
            "request_number": req_number,
            "employee_id": emp_id,
            "employee_name": emp_name,
            "employee_code": emp.get("employee_code") or "",
            "employee_email": emp.get("email") or "",
            "department": emp.get("department") or "Produksi",
            "type": s["type"],
            "type_label": "Kasbon" if s["type"] == "kasbon" else "Pinjaman",
            "amount": amount,
            "purpose": s["purpose"],
            "notes": "",
            "documents": [],
            "installment_count": installment_count,
            "installment_amount": installment_amount,
            "status": s["status"],
            "hr_reviewed_by": "HR Manager" if s["status"] in ("hr_approved", "disbursed", "paid_off") else None,
            "hr_reviewed_at": _now().isoformat() if s["status"] != "submitted" else None,
            "hr_notes": "Disetujui" if s["status"] not in ("submitted", "hr_rejected") else None,
            "disbursed_by": "Finance" if s["status"] in ("disbursed", "paid_off") else None,
            "disbursed_at": _now().isoformat() if s["status"] in ("disbursed", "paid_off") else None,
            "disbursement_date": _now().strftime("%Y-%m-%d") if s["status"] in ("disbursed", "paid_off") else None,
            "deduction_start_period": _now().strftime("%Y-%m") if s["status"] in ("disbursed", "paid_off") else None,
            "finance_notes": "",
            "paid_amount": float(paid),
            "outstanding_balance": float(max(outstanding, 0)),
            "repayments": [{
                "id": _sid(),
                "amount": float(installment_amount),
                "date": _now().strftime("%Y-%m-%d"),
                "method": "payroll_deduction",
                "period": _now().strftime("%Y-%m"),
                "notes": "Auto-potong gaji",
                "by": "Payroll System",
                "created_at": _now().isoformat(),
            }] if paid > 0 else [],
            "submitted_by": emp.get("email") or "staff@dewi.com",
            "submitted_by_name": emp_name,
            "created_at": _now().isoformat(),
            "updated_at": _now().isoformat(),
        }
        await db.dewi_kasbon_requests.insert_one(doc)

    return {"ok": True, "message": f"Demo kasbon selesai ({len(samples)} data)"}
