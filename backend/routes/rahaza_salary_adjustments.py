"""
PT Rahaza / CV. Dewi Aditya — Salary Adjustment & Raise Proposals
Sprint 43 — P0 Critical: KPI Grade → Auto Salary Raise with Multi-Level Approval

Workflow:
  1. KPI Grade A/B published → auto-create raise proposal (status: pending_manager)
  2. Manager/Atasan approve → status: pending_hr
  3. HR approve → status: approved → apply to payroll profile
  4. Either party can reject → status: rejected

Collections:
  - rahaza_salary_adjustments: Raise proposals with approval tracking
  - rahaza_employees: Manager assignment (manager_id field)
"""
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Request, HTTPException
from database import get_db
from auth import require_auth, serialize_doc, log_activity

router = APIRouter(prefix="/api/rahaza", tags=["rahaza-salary"])


def _uid(): return str(uuid.uuid4())
def _now(): return datetime.now(timezone.utc)


ADJUSTMENT_STATUSES = ["pending_manager", "pending_hr", "approved", "rejected", "cancelled"]
ADJUSTMENT_TYPES = ["kpi_raise", "performance_raise", "promotion", "annual_increment", "manual"]


async def _require_hr(request: Request):
    user = await require_auth(request)
    role = (user.get("role") or "").lower()
    if role in ("superadmin", "admin", "owner", "hr", "manager"):
        return user
    perms = user.get("_permissions") or []
    if "*" in perms or "hr.manage" in perms or "salary.manage" in perms:
        return user
    raise HTTPException(403, "Forbidden: butuh akses HR/Manager.")


# ══════════════════════════════════════════════════════════════════════════════
# LIST & GET
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/salary-adjustments")
async def list_adjustments(
    request: Request,
    status: Optional[str] = None,
    employee_id: Optional[str] = None,
    adjustment_type: Optional[str] = None,
):
    """List all salary adjustment proposals (HR/Manager view)"""
    user = await require_auth(request)
    db = get_db()
    
    q = {}
    if status:
        q["status"] = status
    if employee_id:
        q["employee_id"] = employee_id
    if adjustment_type:
        q["adjustment_type"] = adjustment_type
    
    # Filter by role: managers only see their team's proposals
    role = (user.get("role") or "").lower()
    if role not in ("superadmin", "admin", "owner", "hr"):
        # Show proposals where this user is the manager
        my_emp = await db.rahaza_employees.find_one({"user_id": user["id"]}, {"_id": 0, "id": 1})
        if my_emp:
            q["manager_id"] = my_emp["id"]
    
    docs = await db.rahaza_salary_adjustments.find(q, {"_id": 0}).sort("created_at", -1).to_list(100)
    
    # Enrich with employee names
    emp_ids = list({d["employee_id"] for d in docs if d.get("employee_id")})
    emps = await db.rahaza_employees.find(
        {"id": {"$in": emp_ids}}, {"_id": 0, "id": 1, "name": 1, "employee_code": 1}
    ).to_list(500) if emp_ids else []
    emp_map = {e["id"]: e for e in emps}
    
    for d in docs:
        emp = emp_map.get(d.get("employee_id")) or {}
        d["employee_name"] = emp.get("name", "?")
        d["employee_code"] = emp.get("employee_code", "-")
    
    return serialize_doc(docs)


@router.get("/salary-adjustments/{adj_id}")
async def get_adjustment(adj_id: str, request: Request):
    """Get adjustment detail"""
    await require_auth(request)
    db = get_db()
    doc = await db.rahaza_salary_adjustments.find_one({"id": adj_id}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Adjustment tidak ditemukan.")
    
    # Enrich with employee name
    if doc.get("employee_id"):
        emp = await db.rahaza_employees.find_one({"id": doc["employee_id"]}, {"_id": 0})
        doc["employee_name"] = emp.get("name", "?") if emp else "?"
        doc["employee_code"] = emp.get("employee_code", "-") if emp else "-"
    
    return serialize_doc(doc)


# ══════════════════════════════════════════════════════════════════════════════
# CREATE (Manual by HR)
# ══════════════════════════════════════════════════════════════════════════════

@router.post("/salary-adjustments")
async def create_adjustment(request: Request):
    """Create salary adjustment proposal manually (HR only)"""
    user = await _require_hr(request)
    db = get_db()
    body = await request.json()
    
    employee_id = body.get("employee_id")
    if not employee_id:
        raise HTTPException(400, "employee_id wajib.")
    
    emp = await db.rahaza_employees.find_one({"id": employee_id}, {"_id": 0})
    if not emp:
        raise HTTPException(404, "Employee tidak ditemukan.")
    
    # Get current payroll profile
    profile = await db.rahaza_payroll_profiles.find_one(
        {"employee_id": employee_id, "active": True}, {"_id": 0}
    )
    current_base = float(profile.get("base_rate", 0)) if profile else 0
    
    # Calculate new base
    proposed_base = float(body.get("proposed_base") or 0)
    if proposed_base <= current_base:
        raise HTTPException(400, "Proposed base harus lebih besar dari current base.")
    
    raise_amount = proposed_base - current_base
    raise_pct = round((raise_amount / current_base) * 100, 2) if current_base > 0 else 0
    
    # Get manager from employee record
    manager_id = emp.get("manager_id")
    manager_name = None
    if manager_id:
        mgr = await db.rahaza_employees.find_one({"id": manager_id}, {"_id": 0})
        manager_name = mgr.get("name") if mgr else None
    
    doc = {
        "id": _uid(),
        "employee_id": employee_id,
        "employee_name": emp.get("name"),
        "employee_code": emp.get("employee_code"),
        "department": emp.get("department"),
        "manager_id": manager_id,
        "manager_name": manager_name,
        "adjustment_type": body.get("adjustment_type") or "manual",
        "current_base": current_base,
        "proposed_base": proposed_base,
        "raise_amount": raise_amount,
        "raise_pct": raise_pct,
        "reason": body.get("reason") or "Manual adjustment by HR",
        "kpi_period_id": body.get("kpi_period_id"),  # Optional reference
        "performance_cycle_id": body.get("performance_cycle_id"),  # Optional reference
        "effective_date": body.get("effective_date"),  # When raise takes effect
        "status": "pending_manager" if manager_id else "pending_hr",  # Skip manager if no manager assigned
        "created_at": _now(),
        "created_by": user["id"],
        "created_by_name": user.get("name", ""),
        "updated_at": _now(),
    }
    
    await db.rahaza_salary_adjustments.insert_one(doc)
    await log_activity(user["id"], user.get("name", ""), "create", "rahaza.salary_adjustment", f"{emp.get('name')} - {raise_pct}%")
    
    # Send notification to manager (if exists)
    if manager_id:
        try:
            await _notify_manager_approval_needed(db, doc)
        except Exception as e:
            logging.getLogger(__name__).warning(f"Failed to send notification: {e}")
    
    return serialize_doc(doc)


# ══════════════════════════════════════════════════════════════════════════════
# APPROVE (Manager → HR → Applied)
# ══════════════════════════════════════════════════════════════════════════════

@router.post("/salary-adjustments/{adj_id}/approve-manager")
async def approve_by_manager(adj_id: str, request: Request):
    """Manager approval (step 1)"""
    user = await require_auth(request)
    db = get_db()
    body = await request.json()
    
    doc = await db.rahaza_salary_adjustments.find_one({"id": adj_id}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Adjustment tidak ditemukan.")
    
    if doc.get("status") != "pending_manager":
        raise HTTPException(400, f"Status harus 'pending_manager', saat ini: '{doc.get('status')}'")
    
    # Verify user is the assigned manager
    my_emp = await db.rahaza_employees.find_one({"user_id": user["id"]}, {"_id": 0, "id": 1})
    if not my_emp or my_emp["id"] != doc.get("manager_id"):
        # Allow HR/Admin to bypass
        role = (user.get("role") or "").lower()
        if role not in ("superadmin", "admin", "owner", "hr"):
            raise HTTPException(403, "Hanya manager yang assigned yang bisa approve.")
    
    await db.rahaza_salary_adjustments.update_one(
        {"id": adj_id},
        {"$set": {
            "status": "pending_hr",
            "manager_approved_at": _now(),
            "manager_approved_by": user["id"],
            "manager_approved_by_name": user.get("name", ""),
            "manager_notes": body.get("notes") or "",
            "updated_at": _now(),
        }}
    )
    
    await log_activity(user["id"], user.get("name", ""), "approve_manager", "rahaza.salary_adjustment", adj_id)
    
    # Notify HR
    try:
        await _notify_hr_approval_needed(db, doc)
    except Exception as e:
        logging.getLogger(__name__).warning(f"Failed to send notification: {e}")
    
    return {"ok": True, "message": "Approved oleh manager. Menunggu approval HR."}


@router.post("/salary-adjustments/{adj_id}/approve-hr")
async def approve_by_hr(adj_id: str, request: Request):
    """HR approval (step 2) — APPLY to payroll profile"""
    user = await _require_hr(request)
    db = get_db()
    body = await request.json()
    
    doc = await db.rahaza_salary_adjustments.find_one({"id": adj_id}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Adjustment tidak ditemukan.")
    
    # Allow HR to approve even if still pending_manager (override)
    if doc.get("status") not in ("pending_manager", "pending_hr"):
        raise HTTPException(400, f"Status harus 'pending_manager' atau 'pending_hr', saat ini: '{doc.get('status')}'")
    
    # Apply to payroll profile
    profile = await db.rahaza_payroll_profiles.find_one(
        {"employee_id": doc["employee_id"], "active": True}, {"_id": 0}
    )
    
    if profile:
        await db.rahaza_payroll_profiles.update_one(
            {"id": profile["id"]},
            {"$set": {
                "base_rate": doc["proposed_base"],
                "updated_at": _now(),
                "updated_by": user["id"],
                "updated_by_name": user.get("name", ""),
            }}
        )
    else:
        raise HTTPException(404, "Payroll profile tidak ditemukan untuk employee ini.")
    
    # Update adjustment status
    await db.rahaza_salary_adjustments.update_one(
        {"id": adj_id},
        {"$set": {
            "status": "approved",
            "hr_approved_at": _now(),
            "hr_approved_by": user["id"],
            "hr_approved_by_name": user.get("name", ""),
            "hr_notes": body.get("notes") or "",
            "applied_at": _now(),
            "updated_at": _now(),
        }}
    )
    
    await log_activity(user["id"], user.get("name", ""), "approve_hr", "rahaza.salary_adjustment", 
                      f"{doc.get('employee_name')} - {doc.get('raise_pct')}% applied")
    
    # Notify employee (optional)
    try:
        await _notify_employee_raise_approved(db, doc)
    except Exception as e:
        logging.getLogger(__name__).warning(f"Failed to send notification: {e}")
    
    return {"ok": True, "message": f"Approved oleh HR. Raise {doc.get('raise_pct')}% telah diterapkan ke payroll profile."}


# ══════════════════════════════════════════════════════════════════════════════
# REJECT
# ══════════════════════════════════════════════════════════════════════════════

@router.post("/salary-adjustments/{adj_id}/reject")
async def reject_adjustment(adj_id: str, request: Request):
    """Reject adjustment (Manager or HR can reject)"""
    user = await require_auth(request)
    db = get_db()
    body = await request.json()
    
    doc = await db.rahaza_salary_adjustments.find_one({"id": adj_id}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Adjustment tidak ditemukan.")
    
    if doc.get("status") in ("approved", "rejected", "cancelled"):
        raise HTTPException(400, f"Tidak bisa reject adjustment dengan status '{doc.get('status')}'")
    
    # Verify permission
    role = (user.get("role") or "").lower()
    my_emp = await db.rahaza_employees.find_one({"user_id": user["id"]}, {"_id": 0, "id": 1})
    
    is_hr = role in ("superadmin", "admin", "owner", "hr")
    is_manager = my_emp and my_emp["id"] == doc.get("manager_id")
    
    if not (is_hr or is_manager):
        raise HTTPException(403, "Hanya manager atau HR yang bisa reject.")
    
    rejected_by = "HR" if is_hr else "Manager"
    
    await db.rahaza_salary_adjustments.update_one(
        {"id": adj_id},
        {"$set": {
            "status": "rejected",
            "rejected_at": _now(),
            "rejected_by": user["id"],
            "rejected_by_name": user.get("name", ""),
            "rejected_by_role": rejected_by,
            "rejection_reason": body.get("reason") or "Tidak ada alasan",
            "updated_at": _now(),
        }}
    )
    
    await log_activity(user["id"], user.get("name", ""), "reject", "rahaza.salary_adjustment", adj_id)
    
    return {"ok": True, "message": f"Adjustment ditolak oleh {rejected_by}."}


# ══════════════════════════════════════════════════════════════════════════════
# DELETE (Cancel before approval)
# ══════════════════════════════════════════════════════════════════════════════

@router.delete("/salary-adjustments/{adj_id}")
async def cancel_adjustment(adj_id: str, request: Request):
    """Cancel/delete adjustment (only if not yet approved)"""
    await _require_hr(request)
    db = get_db()
    
    doc = await db.rahaza_salary_adjustments.find_one({"id": adj_id}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Adjustment tidak ditemukan.")
    
    if doc.get("status") == "approved":
        raise HTTPException(400, "Tidak bisa cancel adjustment yang sudah approved. Buat adjustment baru untuk reversal.")
    
    await db.rahaza_salary_adjustments.update_one(
        {"id": adj_id},
        {"$set": {"status": "cancelled", "updated_at": _now()}}
    )
    
    return {"ok": True, "message": "Adjustment dibatalkan."}


# ══════════════════════════════════════════════════════════════════════════════
# BULK GENERATE FROM KPI (Manual trigger by HR)
# ══════════════════════════════════════════════════════════════════════════════

def _grade_to_raise_pct(grade: str) -> float:
    """Mirror logic from dewi_kpi._grade — A=10%, B=7%, C/D/E=0%."""
    g = (grade or "").upper()
    if g == "A":
        return 10.0
    if g == "B":
        return 7.0
    return 0.0


@router.post("/salary-adjustments/generate-from-kpi/{period_id}")
async def generate_from_kpi(period_id: str, request: Request):
    """
    Bulk-generate raise proposals from a published KPI period.
    Idempotent: skip employees who already have an active proposal for this period.
    
    Flow:
      - Verify KPI period is published
      - Fetch all KPI results with grade A or B
      - For each, calculate proposed_base from current payroll profile
      - Create proposal with status pending_manager (or pending_hr if no manager)
      - Skip duplicates (existing pending or approved proposal for same employee + period)
    """
    user = await _require_hr(request)
    db = get_db()
    
    # Verify period exists and is published
    period = await db.da_kpi_periods.find_one({"period_id": period_id}, {"_id": 0})
    if not period:
        raise HTTPException(404, "Periode KPI tidak ditemukan.")
    if period.get("status") != "finalized":
        raise HTTPException(400, "Periode KPI harus sudah difinalisasi/publish dulu.")
    
    # Fetch eligible KPI results (grade A or B, published)
    results = await db.da_kpi_results.find(
        {"period_id": period_id, "grade": {"$in": ["A", "B"]}, "publish_status": "published"},
        {"_id": 0}
    ).to_list(500)
    
    if not results:
        return {
            "ok": True,
            "created": 0,
            "skipped": 0,
            "skipped_reasons": {},
            "message": "Tidak ada karyawan dengan grade A/B published pada periode ini.",
        }
    
    created = []
    skipped = []
    skipped_reasons = {
        "duplicate_active": 0,
        "no_payroll_profile": 0,
        "employee_not_found": 0,
        "raise_pct_zero": 0,
    }
    
    for r in results:
        emp_id = r.get("employee_id")
        if not emp_id:
            continue
        
        grade = r.get("grade")
        raise_pct = float(r.get("raise_pct") or _grade_to_raise_pct(grade))
        if raise_pct <= 0:
            skipped_reasons["raise_pct_zero"] += 1
            skipped.append({"employee_id": emp_id, "reason": "raise_pct_zero"})
            continue
        
        # Idempotency check: skip if already has active proposal for this period
        existing = await db.rahaza_salary_adjustments.find_one(
            {
                "employee_id": emp_id,
                "kpi_period_id": period_id,
                "status": {"$in": ["pending_manager", "pending_hr", "approved"]},
            },
            {"_id": 0, "id": 1, "status": 1}
        )
        if existing:
            skipped_reasons["duplicate_active"] += 1
            skipped.append({"employee_id": emp_id, "reason": "duplicate_active", "existing_id": existing["id"]})
            continue
        
        emp = await db.rahaza_employees.find_one({"id": emp_id}, {"_id": 0})
        if not emp:
            skipped_reasons["employee_not_found"] += 1
            skipped.append({"employee_id": emp_id, "reason": "employee_not_found"})
            continue
        
        # Get current payroll profile
        profile = await db.rahaza_payroll_profiles.find_one(
            {"employee_id": emp_id, "active": True}, {"_id": 0}
        )
        if not profile:
            skipped_reasons["no_payroll_profile"] += 1
            skipped.append({"employee_id": emp_id, "reason": "no_payroll_profile"})
            continue
        
        current_base = float(profile.get("base_rate") or 0)
        if current_base <= 0:
            skipped_reasons["no_payroll_profile"] += 1
            skipped.append({"employee_id": emp_id, "reason": "no_payroll_profile"})
            continue
        
        raise_amount = round(current_base * (raise_pct / 100.0), 2)
        proposed_base = round(current_base + raise_amount, 2)
        
        # Get manager
        manager_id = emp.get("manager_id")
        manager_name = None
        if manager_id:
            mgr = await db.rahaza_employees.find_one({"id": manager_id}, {"_id": 0, "name": 1})
            manager_name = mgr.get("name") if mgr else None
        
        doc = {
            "id": _uid(),
            "employee_id": emp_id,
            "employee_name": emp.get("name"),
            "employee_code": emp.get("employee_code"),
            "department": emp.get("department"),
            "manager_id": manager_id,
            "manager_name": manager_name,
            "adjustment_type": "kpi_raise",
            "current_base": current_base,
            "proposed_base": proposed_base,
            "raise_amount": raise_amount,
            "raise_pct": raise_pct,
            "reason": f"Auto-generated dari KPI Grade {grade} (Score: {r.get('kpi_final')}) — Periode {period.get('period_label') or period_id}",
            "kpi_period_id": period_id,
            "kpi_grade": grade,
            "kpi_final_score": r.get("kpi_final"),
            "performance_cycle_id": None,
            "effective_date": None,
            "status": "pending_manager" if manager_id else "pending_hr",
            "created_at": _now(),
            "created_by": user["id"],
            "created_by_name": user.get("name", ""),
            "updated_at": _now(),
        }
        
        await db.rahaza_salary_adjustments.insert_one(doc)
        created.append({
            "id": doc["id"],
            "employee_id": emp_id,
            "employee_name": emp.get("name"),
            "raise_pct": raise_pct,
            "manager_id": manager_id,
            "status": doc["status"],
        })
        
        # Notify manager if exists
        if manager_id:
            try:
                await _notify_manager_approval_needed(db, doc)
            except Exception as e:
                logging.getLogger(__name__).warning(f"Failed to send notification: {e}")
    
    await log_activity(
        user["id"], user.get("name", ""), "generate_from_kpi", "rahaza.salary_adjustment",
        f"Period {period_id} — Created: {len(created)}, Skipped: {len(skipped)}"
    )
    
    return {
        "ok": True,
        "period_id": period_id,
        "period_label": period.get("period_label"),
        "created": len(created),
        "skipped": len(skipped),
        "skipped_reasons": skipped_reasons,
        "created_items": created,
        "message": f"Berhasil generate {len(created)} usulan kenaikan gaji. {len(skipped)} di-skip.",
    }


# ══════════════════════════════════════════════════════════════════════════════
# MY APPROVALS (Inbox for Managers)
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/salary-adjustments/my/pending-approvals")
async def my_pending_approvals(request: Request):
    """List proposals where current user is the assigned manager and status=pending_manager."""
    user = await require_auth(request)
    db = get_db()
    
    # Find user's employee record
    my_emp = await db.rahaza_employees.find_one({"user_id": user["id"]}, {"_id": 0, "id": 1})
    if not my_emp:
        return []
    
    docs = await db.rahaza_salary_adjustments.find(
        {"manager_id": my_emp["id"], "status": "pending_manager"},
        {"_id": 0}
    ).sort("created_at", -1).to_list(100)
    
    return serialize_doc(docs)


# ══════════════════════════════════════════════════════════════════════════════
# STATS & SUMMARY
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/salary-adjustments/stats/summary")
async def adjustment_stats(request: Request):
    """Summary stats for salary adjustments"""
    await require_auth(request)
    db = get_db()
    
    total = await db.rahaza_salary_adjustments.count_documents({})
    pending_manager = await db.rahaza_salary_adjustments.count_documents({"status": "pending_manager"})
    pending_hr = await db.rahaza_salary_adjustments.count_documents({"status": "pending_hr"})
    approved = await db.rahaza_salary_adjustments.count_documents({"status": "approved"})
    rejected = await db.rahaza_salary_adjustments.count_documents({"status": "rejected"})
    
    # Average raise %
    pipeline = [
        {"$match": {"status": "approved"}},
        {"$group": {"_id": None, "avg_raise_pct": {"$avg": "$raise_pct"}}}
    ]
    avg_result = await db.rahaza_salary_adjustments.aggregate(pipeline).to_list(1)
    avg_raise_pct = round(avg_result[0]["avg_raise_pct"], 2) if avg_result else 0
    
    return {
        "total": total,
        "pending_manager": pending_manager,
        "pending_hr": pending_hr,
        "approved": approved,
        "rejected": rejected,
        "avg_raise_pct": avg_raise_pct,
    }


# ══════════════════════════════════════════════════════════════════════════════
# NOTIFICATION HELPERS (Integration with rahaza_notifications)
# ══════════════════════════════════════════════════════════════════════════════

async def _notify_manager_approval_needed(db, adjustment: dict):
    """Send notification to manager when new raise proposal is created (SSOT type='rahaza')."""
    manager_id = adjustment.get("manager_id")
    if not manager_id:
        return
    
    mgr_emp = await db.rahaza_employees.find_one({"id": manager_id}, {"_id": 0, "user_id": 1})
    if not mgr_emp or not mgr_emp.get("user_id"):
        return
    
    from routes.rahaza_notifications import publish_notification
    await publish_notification(
        db,
        type_="salary_raise_approval",
        severity="info",
        title="Approval Kenaikan Gaji Diperlukan",
        message=(
            f"Proposal kenaikan gaji untuk {adjustment.get('employee_name')} "
            f"({adjustment.get('raise_pct')}%) menunggu approval Anda."
        ),
        link_module="hr_salary_adjustments",
        link_id=adjustment["id"],
        target_user_ids=[mgr_emp["user_id"]],
    )


async def _notify_hr_approval_needed(db, adjustment: dict):
    """Send notification to HR when manager has approved (SSOT type='rahaza')."""
    from routes.rahaza_notifications import publish_notification
    # Find all HR users
    hr_users = await db.users.find(
        {"role": {"$in": ["hr", "admin", "superadmin", "owner"]}},
        {"_id": 0, "id": 1}
    ).to_list(500)
    
    user_ids = [u["id"] for u in hr_users if u.get("id")]
    if not user_ids:
        return
    await publish_notification(
        db,
        type_="salary_raise_hr_approval",
        severity="info",
        title="Approval HR: Kenaikan Gaji",
        message=(
            f"Proposal kenaikan gaji {adjustment.get('employee_name')} "
            f"({adjustment.get('raise_pct')}%) sudah disetujui manager. Menunggu approval HR."
        ),
        link_module="hr_salary_adjustments",
        link_id=adjustment["id"],
        target_user_ids=user_ids,
        target_roles=["hr", "admin", "superadmin", "owner"],
    )


async def _notify_employee_raise_approved(db, adjustment: dict):
    """Send notification to employee when raise is approved (SSOT type='rahaza')."""
    from routes.rahaza_notifications import publish_notification
    emp = await db.rahaza_employees.find_one(
        {"id": adjustment["employee_id"]}, {"_id": 0, "user_id": 1}
    )
    if not emp or not emp.get("user_id"):
        return
    
    await publish_notification(
        db,
        type_="salary_raise_approved",
        severity="success",
        title="Selamat! Kenaikan Gaji Disetujui",
        message=(
            f"Proposal kenaikan gaji Anda sebesar {adjustment.get('raise_pct')}% "
            f"telah disetujui. Efektif mulai periode payroll berikutnya."
        ),
        link_module="my_profile",
        link_id=adjustment["id"],
        target_user_ids=[emp["user_id"]],
    )
