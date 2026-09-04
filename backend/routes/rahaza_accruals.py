"""
CV. Dewi Aditya ERP — Accruals & Provisions Module (Phase 8C)

Endpoints (prefix /api/rahaza/finance):
  GET    /accruals                      — list accrual entries
  POST   /accruals                      — create accrual entry
  GET    /accruals/{id}                 — detail
  PUT    /accruals/{id}                 — update draft
  DELETE /accruals/{id}                 — delete draft
  POST   /accruals/{id}/post            — post ke GL (with auto-reversal next period)
  POST   /accruals/{id}/reverse         — manual reverse
  POST   /accruals/create-recurring     — create next month recurring accruals
  GET    /accruals/recurring-templates  — list recurring templates

Collection: rahaza_accruals

Accrual Types:
- utility (Listrik, Air, Telepon)
- rent (Sewa)
- professional_fees (Jasa Profesional)
- interest_payable (Bunga Hutang)
- salary_bonus (Bonus Karyawan)
- other (Lain-lain)

Recurring Accruals:
- User bisa mark accrual sebagai "recurring"
- Nominal bisa beda setiap bulan (tidak fixed)
- User trigger manual: create_recurring untuk generate next period
"""
from fastapi import APIRouter, Request, HTTPException
from database import get_db
from auth import require_auth, serialize_doc, log_activity
from datetime import datetime, timezone, date
from dateutil.relativedelta import relativedelta
from typing import Optional
import uuid
import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/rahaza/finance", tags=["rahaza-accruals"])

def _uid(): return str(uuid.uuid4())
def _now(): return datetime.now(timezone.utc)

ACCRUAL_TYPES = ["utility", "rent", "professional_fees", "interest_payable", "salary_bonus", "tax_payable", "other"]
ACCRUAL_STATUSES = ["draft", "posted", "reversed"]


# ─── CRUD ENDPOINTS ────────────────────────────────────────────────────────────

@router.get("/accruals")
async def list_accruals(request: Request, 
                        period: Optional[str] = None,
                        accrual_type: Optional[str] = None,
                        status: Optional[str] = None,
                        recurring_only: Optional[bool] = None):
    await require_auth(request)
    db = get_db()
    
    q = {}
    if period:
        q["period"] = period
    if accrual_type:
        q["accrual_type"] = accrual_type
    if status:
        q["status"] = status
    if recurring_only is not None:
        q["is_recurring"] = recurring_only
    
    rows = await db.rahaza_accruals.find(q, {"_id": 0}).sort("period", -1).to_list(500)
    return serialize_doc(rows)


@router.post("/accruals")
async def create_accrual(request: Request):
    user = await require_auth(request)
    db = get_db()
    body = await request.json()
    
    period = body.get("period", date.today().strftime("%Y-%m"))
    accrual_type = body.get("accrual_type", "other")
    amount = float(body.get("amount", 0))
    
    if amount <= 0:
        raise HTTPException(400, "Amount harus > 0")
    
    if accrual_type not in ACCRUAL_TYPES:
        raise HTTPException(400, f"Invalid accrual_type. Must be one of: {', '.join(ACCRUAL_TYPES)}")
    
    # Validate period format
    try:
        datetime.strptime(period, "%Y-%m")
    except ValueError:
        raise HTTPException(400, "Invalid period format. Use YYYY-MM")
    
    doc = {
        "id": _uid(),
        "period": period,
        "accrual_type": accrual_type,
        "description": body.get("description", ""),
        "amount": round(amount, 2),
        "expense_account": body.get("expense_account", ""),  # User can specify custom GL account
        "accrued_account": body.get("accrued_account", ""),
        "status": "draft",
        "is_recurring": body.get("is_recurring", False),
        "recurring_template_id": body.get("recurring_template_id") or None,
        "posted_at": None,
        "posted_by": None,
        "je_id": None,
        "je_number": None,
        "reversal_period": None,
        "reversed_at": None,
        "reversed_by": None,
        "reversal_je_id": None,
        "reversal_je_number": None,
        "notes": body.get("notes", ""),
        "created_at": _now(),
        "updated_at": _now(),
        "created_by": user.get("id"),
        "created_by_name": user.get("name", ""),
    }
    
    await db.rahaza_accruals.insert_one(doc)
    await log_activity(user["id"], user.get("name", ""), "create", "accruals",
                      f"Created accrual {accrual_type} for {period}: Rp {amount:,.0f}")
    
    return serialize_doc(doc)


@router.get("/accruals/recurring-templates")
async def list_recurring_templates(request: Request):
    """List all accruals marked as recurring (as templates for future periods)"""
    await require_auth(request)
    db = get_db()
    
    templates = await db.rahaza_accruals.find(
        {"is_recurring": True},
        {"_id": 0}
    ).sort("period", -1).to_list(500)
    
    return serialize_doc(templates)


@router.get("/accruals/{accrual_id}")
async def get_accrual(accrual_id: str, request: Request):
    await require_auth(request)
    db = get_db()
    
    doc = await db.rahaza_accruals.find_one({"id": accrual_id}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Accrual not found")
    
    return serialize_doc(doc)


@router.put("/accruals/{accrual_id}")
async def update_accrual(accrual_id: str, request: Request):
    await require_auth(request)
    db = get_db()
    body = await request.json()
    
    existing = await db.rahaza_accruals.find_one({"id": accrual_id})
    if not existing:
        raise HTTPException(404, "Accrual not found")
    
    if existing.get("status") != "draft":
        raise HTTPException(400, "Only draft accruals can be updated")
    
    updates = {"updated_at": _now()}
    
    if "description" in body:
        updates["description"] = body["description"]
    if "amount" in body:
        updates["amount"] = round(float(body["amount"]), 2)
    if "expense_account" in body:
        updates["expense_account"] = body["expense_account"]
    if "accrued_account" in body:
        updates["accrued_account"] = body["accrued_account"]
    if "is_recurring" in body:
        updates["is_recurring"] = body["is_recurring"]
    if "notes" in body:
        updates["notes"] = body["notes"]
    
    await db.rahaza_accruals.update_one({"id": accrual_id}, {"$set": updates})
    updated = await db.rahaza_accruals.find_one({"id": accrual_id}, {"_id": 0})
    
    return serialize_doc(updated)


@router.delete("/accruals/{accrual_id}")
async def delete_accrual(accrual_id: str, request: Request):
    user = await require_auth(request)
    db = get_db()
    
    existing = await db.rahaza_accruals.find_one({"id": accrual_id})
    if not existing:
        raise HTTPException(404, "Accrual not found")
    
    if existing.get("status") != "draft":
        raise HTTPException(400, "Only draft accruals can be deleted")
    
    await db.rahaza_accruals.delete_one({"id": accrual_id})
    await log_activity(user["id"], user.get("name", ""), "delete", "accruals",
                      f"Deleted accrual {existing.get('accrual_type')} for {existing.get('period')}")
    
    return {"ok": True, "message": "Accrual deleted"}


# ─── POSTING & REVERSAL ────────────────────────────────────────────────────────

@router.post("/accruals/{accrual_id}/post")
async def post_accrual(accrual_id: str, request: Request):
    """
    Post accrual ke GL. Dr. Expense / Cr. Accrued Expenses.
    Auto-create reversal entry for next period.
    """
    user = await require_auth(request)
    db = get_db()
    
    accrual = await db.rahaza_accruals.find_one({"id": accrual_id}, {"_id": 0})
    if not accrual:
        raise HTTPException(404, "Accrual not found")
    
    if accrual.get("status") != "draft":
        raise HTTPException(400, f"Accrual already {accrual.get('status')}")
    
    # Post to GL
    try:
        from routes.rahaza_posting import post_accrual_expense
        posting_result = await post_accrual_expense(db, accrual, user)
        
        if not posting_result.get("ok"):
            raise HTTPException(400, f"Posting failed: {posting_result.get('error')}")
        
        # Calculate reversal period (next month)
        period_date = datetime.strptime(accrual["period"], "%Y-%m").date()
        next_period_date = period_date + relativedelta(months=1)
        reversal_period = next_period_date.strftime("%Y-%m")
        
        # Update status
        await db.rahaza_accruals.update_one(
            {"id": accrual_id},
            {"$set": {
                "status": "posted",
                "posted_at": _now(),
                "posted_by": user.get("id"),
                "je_id": posting_result.get("je_id"),
                "je_number": posting_result.get("je_number"),
                "reversal_period": reversal_period,
            }}
        )
        
        await log_activity(user["id"], user.get("name", ""), "post_accrual", "accruals",
                          f"Posted accrual {accrual['accrual_type']} for {accrual['period']}: JE {posting_result.get('je_number')}")
        
        updated = await db.rahaza_accruals.find_one({"id": accrual_id}, {"_id": 0})
        return serialize_doc(updated)
        
    except Exception as e:
        logger.exception("Failed to post accrual")
        raise HTTPException(500, str(e))


@router.post("/accruals/{accrual_id}/reverse")
async def reverse_accrual(accrual_id: str, request: Request):
    """
    Reverse accrual entry. Dr. Accrued Expenses / Cr. Expense.
    """
    user = await require_auth(request)
    db = get_db()
    
    accrual = await db.rahaza_accruals.find_one({"id": accrual_id}, {"_id": 0})
    if not accrual:
        raise HTTPException(404, "Accrual not found")
    
    if accrual.get("status") != "posted":
        raise HTTPException(400, "Only posted accruals can be reversed")
    
    if accrual.get("reversed_at"):
        raise HTTPException(400, "Accrual already reversed")
    
    # Post reversal to GL
    try:
        from routes.rahaza_posting import post_accrual_reversal
        reversal_result = await post_accrual_reversal(db, accrual, user)
        
        if not reversal_result.get("ok"):
            raise HTTPException(400, f"Reversal posting failed: {reversal_result.get('error')}")
        
        # Update status
        await db.rahaza_accruals.update_one(
            {"id": accrual_id},
            {"$set": {
                "status": "reversed",
                "reversed_at": _now(),
                "reversed_by": user.get("id"),
                "reversal_je_id": reversal_result.get("je_id"),
                "reversal_je_number": reversal_result.get("je_number"),
            }}
        )
        
        await log_activity(user["id"], user.get("name", ""), "reverse_accrual", "accruals",
                          f"Reversed accrual {accrual['accrual_type']} for {accrual['period']}: JE {reversal_result.get('je_number')}")
        
        updated = await db.rahaza_accruals.find_one({"id": accrual_id}, {"_id": 0})
        return serialize_doc(updated)
        
    except Exception as e:
        logger.exception("Failed to reverse accrual")
        raise HTTPException(500, str(e))


# ─── RECURRING ACCRUALS ────────────────────────────────────────────────────────

@router.post("/accruals/create-recurring")
async def create_recurring_accruals(request: Request):
    """
    Create next month accruals dari recurring templates.
    
    Body:
    {
        "target_period": "2026-06",  // Period untuk create accrual baru
        "template_ids": []            // Optional: kosong = semua recurring templates
    }
    
    Returns: list accruals yang dibuat
    """
    user = await require_auth(request)
    db = get_db()
    body = await request.json()
    
    target_period = body.get("target_period")
    if not target_period:
        # Default: next month
        next_month = date.today() + relativedelta(months=1)
        target_period = next_month.strftime("%Y-%m")
    
    template_ids = body.get("template_ids", [])
    
    # Get recurring templates
    query = {"is_recurring": True, "status": {"$ne": "draft"}}  # Only use posted/reversed as templates
    if template_ids:
        query["id"] = {"$in": template_ids}
    
    templates = await db.rahaza_accruals.find(query, {"_id": 0}).to_list(500)
    
    if not templates:
        return {
            "ok": True,
            "message": "No recurring templates found",
            "created_count": 0,
            "accruals": []
        }
    
    created = []
    
    for template in templates:
        # Check if accrual already exists for this period + type + description
        existing = await db.rahaza_accruals.find_one({
            "period": target_period,
            "accrual_type": template.get("accrual_type"),
            "description": template.get("description"),
            "recurring_template_id": template.get("id"),
        })
        
        if existing:
            logger.info(f"Recurring accrual already exists for {target_period}: {template.get('description')}")
            continue
        
        # Create new accrual (draft, user needs to update amount & post manually)
        new_doc = {
            "id": _uid(),
            "period": target_period,
            "accrual_type": template.get("accrual_type"),
            "description": template.get("description"),
            "amount": template.get("amount", 0),  # Copy amount as default, user can modify
            "expense_account": template.get("expense_account", ""),
            "accrued_account": template.get("accrued_account", ""),
            "status": "draft",
            "is_recurring": True,
            "recurring_template_id": template.get("id"),
            "posted_at": None,
            "posted_by": None,
            "je_id": None,
            "je_number": None,
            "reversal_period": None,
            "reversed_at": None,
            "reversed_by": None,
            "reversal_je_id": None,
            "reversal_je_number": None,
            "notes": f"Auto-created from recurring template (period {template.get('period')})",
            "created_at": _now(),
            "updated_at": _now(),
            "created_by": user.get("id"),
            "created_by_name": user.get("name", ""),
        }
        
        await db.rahaza_accruals.insert_one(new_doc)
        created.append(new_doc)
        logger.info(f"✅ Created recurring accrual for {target_period}: {new_doc['description']}")
    
    await log_activity(user["id"], user.get("name", ""), "create_recurring_accruals", "accruals",
                      f"Created {len(created)} recurring accruals for period {target_period}")
    
    return {
        "ok": True,
        "message": f"Created {len(created)} recurring accruals for period {target_period}",
        "created_count": len(created),
        "accruals": serialize_doc(created),
    }
