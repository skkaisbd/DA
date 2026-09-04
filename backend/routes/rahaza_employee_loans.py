"""
CV. Dewi Aditya ERP — Employee Loan Management (Phase 11A & 11B)

Endpoints (prefix /api/rahaza/hr):
  GET    /employee-loans
  POST   /employee-loans/disburse
  GET    /employee-loans/{id}
  POST   /employee-loans/{id}/repay
  POST   /employee-loans/{id}/deduct-from-payroll  # Auto-called from payroll
  GET    /employee-loans/outstanding-by-employee/{employee_id}

Collection: rahaza_employee_loans

Loan Status:
- active: Loan masih ada outstanding balance
- paid_off: Loan sudah lunas
- written_off: Loan di-write off (tidak ditagih)
"""
from fastapi import APIRouter, Request, HTTPException
from database import get_db
from auth import require_auth, serialize_doc, log_activity
from datetime import datetime, timezone, date
from typing import Optional
import uuid
import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/rahaza/hr", tags=["rahaza-employee-loans"])

def _uid(): return str(uuid.uuid4())
def _now(): return datetime.now(timezone.utc)
def _today_iso(): return date.today().isoformat()

LOAN_STATUSES = ["active", "paid_off", "written_off"]


# ─── DISBURSEMENT ──────────────────────────────────────────────────────────────

@router.post("/employee-loans/disburse")
async def disburse_employee_loan(request: Request):
    """PINTU LAMA — DIMATIKAN (HTTP 410) pada SESI #27.

    Kenapa dimatikan, bukan "dibiarkan saja":
    Pinjaman karyawan sudah dipindahkan ke **Kasbon & Pinjaman**
    (`dewi_kasbon_requests`, modul `hr-kasbon`) lewat migrasi T2.1 sesi #12 —
    koleksi `rahaza_employee_loans` DIARSIPKAN (0 dokumen), menu
    `hr-employee-loans` sudah diarahkan ulang ke `hr-kasbon`, dan layarnya
    (`EmployeeLoansModule.jsx`) sudah dilepas dari registry modul.
    Yang TERTINGGAL adalah endpoint penulis ini. Selama ia hidup:
      · ada DUA pintu membuat pinjaman dengan dua koleksi & dua penomoran ⇒
        "berapa total pinjaman karyawan?" punya dua jawaban;
      · jenis dokumen "Pinjaman Karyawan" versi legacy tetap tampil di layar
        Penomoran Dokumen sehingga owner bisa mengatur nomor untuk dokumen yang
        TIDAK BISA lagi dibuat siapa pun — persis "setelan yang berbohong" yang
        Fase G berusaha hilangkan.
    Endpoint BACA (GET) tetap hidup supaya arsip lama masih bisa dilihat.
    """
    await require_auth(request)
    raise HTTPException(410, (
        "Jalur pinjaman lama sudah tidak dipakai. Buat pengajuan lewat "
        "Kasbon & Pinjaman (POST /api/dewi/kasbon/requests dengan type='pinjaman') "
        "— di layar: Portal Keuangan/SDM → Kasbon & Pinjaman. Data pinjaman lama "
        "tetap bisa dibaca lewat GET /api/rahaza/hr/employee-loans."))


async def _disburse_employee_loan_legacy(request: Request):
    """Isi lama endpoint disburse — disimpan sebagai rujukan, tidak diarahkan router.

    Sengaja TIDAK dihapus: bila suatu saat arsip legacy perlu diisi ulang lewat
    migrasi, logika GL-nya (Dr 1-1320 / Cr 1-110) ada di sini.
    """
    user = await require_auth(request)
    db = get_db()
    body = await request.json()
    
    employee_id = body.get("employee_id")
    loan_amount = float(body.get("loan_amount", 0))
    installment_amount = float(body.get("installment_amount", 0))
    installment_count = int(body.get("installment_count", 0))
    
    if not employee_id:
        raise HTTPException(400, "employee_id wajib diisi")
    
    if loan_amount <= 0:
        raise HTTPException(400, "loan_amount harus > 0")
    
    if installment_amount <= 0 or installment_count <= 0:
        raise HTTPException(400, "installment_amount dan installment_count harus > 0")
    
    # Validate employee exists
    employee = await db.rahaza_employees.find_one({"id": employee_id}, {"_id": 0})
    if not employee:
        raise HTTPException(404, "Employee tidak ditemukan")
    
    disbursement_date = body.get("disbursement_date", _today_iso())
    first_deduction_period = body.get("first_deduction_period")
    
    # Nomor pinjaman legacy — jalur ini tidak lagi dipanggil router (410 di atas).
    from utils.counters import gen_prefixed_number as _gen_loan_no
    loan_number = await _gen_loan_no(db, "rahaza_employee_loans", "loan_number", "LOAN-", 5)
    
    doc = {
        "id": _uid(),
        "loan_number": loan_number,
        "employee_id": employee_id,
        "employee_name": employee.get("name"),
        "loan_amount": round(loan_amount, 2),
        "installment_amount": round(installment_amount, 2),
        "installment_count": installment_count,
        "paid_installments": 0,
        "paid_amount": 0,
        "outstanding_balance": round(loan_amount, 2),
        "disbursement_date": disbursement_date,
        "first_deduction_period": first_deduction_period,
        "status": "active",
        "notes": body.get("notes", ""),
        "disbursed_by": user.get("id"),
        "disbursed_by_name": user.get("name", ""),
        "disbursed_at": _now(),
        "created_at": _now(),
        "updated_at": _now(),
    }
    
    await db.rahaza_employee_loans.insert_one(doc)
    
    # Auto-post GL
    posting_result = None
    try:
        from routes.rahaza_posting import post_employee_loan_disbursement
        loan_refresh = await db.rahaza_employee_loans.find_one({"id": doc["id"]}, {"_id": 0})
        posting_result = await post_employee_loan_disbursement(db, loan_refresh, user)
    except Exception as e:
        logger.exception("Employee loan disbursement GL posting failed")
        posting_result = {"ok": False, "error": str(e)}
    
    # Update with GL info
    if posting_result and posting_result.get("ok"):
        await db.rahaza_employee_loans.update_one(
            {"id": doc["id"]},
            {"$set": {
                "gl_disbursement_je_id": posting_result.get("je_id"),
                "gl_disbursement_je_number": posting_result.get("je_number"),
            }}
        )
    
    await log_activity(
        user.get("id", "system"),
        user.get("name", "system"),
        "disburse_employee_loan",
        "employee_loans",
        f"Disbursed loan {loan_number} to {employee.get('name')}: Rp {loan_amount:,.0f} ({installment_count}x Rp {installment_amount:,.0f})"
    )
    
    final_loan = await db.rahaza_employee_loans.find_one({"id": doc["id"]}, {"_id": 0})
    final_loan["_posting_result"] = posting_result
    return serialize_doc(final_loan)


# ─── REPAYMENT ─────────────────────────────────────────────────────────────────

@router.post("/employee-loans/{loan_id}/repay")
async def manual_loan_repayment(loan_id: str, request: Request):
    """
    Phase 11B: Manual repayment (bukan via payroll, misalnya cash repayment).
    
    Auto-post GL: Dr. Cash (1-110) / Cr. Employee Loan Receivable (1-1320)
    
    Body:
    {
        "repayment_amount": 500000,
        "repayment_date": "2026-06-01",
        "notes": "Bayar tunai"
    }
    """
    user = await require_auth(request)
    db = get_db()
    body = await request.json()
    
    loan = await db.rahaza_employee_loans.find_one({"id": loan_id}, {"_id": 0})
    if not loan:
        raise HTTPException(404, "Loan tidak ditemukan")
    
    if loan.get("status") != "active":
        raise HTTPException(400, f"Loan status {loan.get('status')}, cannot repay")
    
    repayment_amount = float(body.get("repayment_amount", 0))
    outstanding = float(loan.get("outstanding_balance", 0))
    
    if repayment_amount <= 0:
        raise HTTPException(400, "repayment_amount harus > 0")
    
    if repayment_amount > outstanding:
        raise HTTPException(400, f"repayment_amount (Rp {repayment_amount:,.0f}) melebihi outstanding (Rp {outstanding:,.0f})")
    
    repayment_date = body.get("repayment_date", _today_iso())
    
    # Calculate new balances
    new_paid_amount = float(loan.get("paid_amount", 0)) + repayment_amount
    new_outstanding = outstanding - repayment_amount
    new_status = "paid_off" if new_outstanding <= 0.01 else "active"
    
    # Update loan
    await db.rahaza_employee_loans.update_one(
        {"id": loan_id},
        {"$set": {
            "paid_amount": round(new_paid_amount, 2),
            "outstanding_balance": round(new_outstanding, 2),
            "status": new_status,
            "updated_at": _now(),
        }}
    )
    
    # Create repayment record
    repayment_doc = {
        "id": _uid(),
        "loan_id": loan_id,
        "loan_number": loan.get("loan_number"),
        "employee_id": loan.get("employee_id"),
        "repayment_amount": round(repayment_amount, 2),
        "repayment_date": repayment_date,
        "repayment_method": "manual",  # vs "payroll"
        "notes": body.get("notes", ""),
        "created_by": user.get("id"),
        "created_by_name": user.get("name", ""),
        "created_at": _now(),
    }
    
    await db.rahaza_employee_loan_repayments.insert_one(repayment_doc)
    
    await log_activity(
        user.get("id", "system"),
        user.get("name", "system"),
        "repay_employee_loan",
        "employee_loans",
        f"Manual repayment {loan.get('loan_number')}: Rp {repayment_amount:,.0f} (Outstanding: Rp {new_outstanding:,.0f})"
    )
    
    updated_loan = await db.rahaza_employee_loans.find_one({"id": loan_id}, {"_id": 0})
    return serialize_doc(updated_loan)


@router.post("/employee-loans/{loan_id}/deduct-from-payroll")
async def deduct_loan_from_payroll(loan_id: str, request: Request):
    """
    Phase 11B: Deduct loan installment dari payroll.
    Called automatically dari payroll processing.
    
    Auto-post GL: Dr. Salary Payable (2-1200) / Cr. Employee Loan Receivable (1-1320)
    
    Body:
    {
        "payroll_run_id": "...",
        "period": "2026-06",
        "deduction_amount": 500000
    }
    """
    user = await require_auth(request)
    db = get_db()
    body = await request.json()
    
    loan = await db.rahaza_employee_loans.find_one({"id": loan_id}, {"_id": 0})
    if not loan:
        raise HTTPException(404, "Loan tidak ditemukan")
    
    if loan.get("status") != "active":
        return {"ok": False, "message": f"Loan status {loan.get('status')}, skip deduction"}
    
    deduction_amount = float(body.get("deduction_amount", 0))
    outstanding = float(loan.get("outstanding_balance", 0))
    
    if deduction_amount <= 0:
        raise HTTPException(400, "deduction_amount harus > 0")
    
    # Allow deduction even if > outstanding (will be capped)
    actual_deduction = min(deduction_amount, outstanding)
    
    # Calculate new balances
    new_paid_installments = int(loan.get("paid_installments", 0)) + 1
    new_paid_amount = float(loan.get("paid_amount", 0)) + actual_deduction
    new_outstanding = outstanding - actual_deduction
    new_status = "paid_off" if new_outstanding <= 0.01 else "active"
    
    # Update loan
    await db.rahaza_employee_loans.update_one(
        {"id": loan_id},
        {"$set": {
            "paid_installments": new_paid_installments,
            "paid_amount": round(new_paid_amount, 2),
            "outstanding_balance": round(new_outstanding, 2),
            "status": new_status,
            "updated_at": _now(),
        }}
    )
    
    # Create repayment record
    repayment_doc = {
        "id": _uid(),
        "loan_id": loan_id,
        "loan_number": loan.get("loan_number"),
        "employee_id": loan.get("employee_id"),
        "repayment_amount": round(actual_deduction, 2),
        "repayment_date": _today_iso(),
        "repayment_method": "payroll",
        "payroll_run_id": body.get("payroll_run_id"),
        "period": body.get("period"),
        "notes": f"Deduction from payroll {body.get('period')}",
        "created_by": "system",
        "created_by_name": "Payroll System",
        "created_at": _now(),
    }
    
    await db.rahaza_employee_loan_repayments.insert_one(repayment_doc)
    
    # Auto-post GL for payroll deduction
    posting_result = None
    try:
        from routes.rahaza_posting import post_employee_loan_repayment_payroll
        posting_result = await post_employee_loan_repayment_payroll(db, loan, actual_deduction, body.get("period"), user)
    except Exception as e:
        logger.exception("Employee loan repayment (payroll) GL posting failed")
        posting_result = {"ok": False, "error": str(e)}
    
    return {
        "ok": True,
        "deduction_amount": actual_deduction,
        "new_outstanding": round(new_outstanding, 2),
        "status": new_status,
        "posting_result": posting_result
    }


# ─── QUERIES ───────────────────────────────────────────────────────────────────

@router.get("/employee-loans")
async def list_employee_loans(request: Request, status: Optional[str] = None, employee_id: Optional[str] = None):
    await require_auth(request)
    db = get_db()
    
    q = {}
    if status:
        q["status"] = status
    if employee_id:
        q["employee_id"] = employee_id
    
    loans = await db.rahaza_employee_loans.find(q, {"_id": 0}).sort("disbursement_date", -1).to_list(500)
    return serialize_doc(loans)


@router.get("/employee-loans/{loan_id}")
async def get_employee_loan(loan_id: str, request: Request):
    await require_auth(request)
    db = get_db()
    
    loan = await db.rahaza_employee_loans.find_one({"id": loan_id}, {"_id": 0})
    if not loan:
        raise HTTPException(404, "Loan not found")
    
    # Get repayment history
    repayments = await db.rahaza_employee_loan_repayments.find({"loan_id": loan_id}, {"_id": 0}).sort("repayment_date", 1).to_list(100)
    loan["repayments"] = repayments
    
    return serialize_doc(loan)


@router.get("/employee-loans/outstanding-by-employee/{employee_id}")
async def get_outstanding_loans_by_employee(employee_id: str, request: Request):
    """Get all active loans untuk employee (untuk payroll deduction)"""
    await require_auth(request)
    db = get_db()
    
    loans = await db.rahaza_employee_loans.find(
        {"employee_id": employee_id, "status": "active"},
        {"_id": 0}
    ).to_list(100)
    
    total_outstanding = sum(float(loan.get("outstanding_balance", 0)) for loan in loans)
    
    return serialize_doc({
        "employee_id": employee_id,
        "active_loans_count": len(loans),
        "total_outstanding": round(total_outstanding, 2),
        "loans": loans
    })
