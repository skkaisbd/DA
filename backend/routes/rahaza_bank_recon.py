"""
CV. Dewi Aditya ERP — Bank Reconciliation Adjustments (Phase 9B)

Endpoints (prefix /api/rahaza/finance):
  GET    /bank-recon-adjustments
  POST   /bank-recon-adjustments
  GET    /bank-recon-adjustments/{id}
  PUT    /bank-recon-adjustments/{id}
  DELETE /bank-recon-adjustments/{id}
  POST   /bank-recon-adjustments/{id}/post

Collection: rahaza_bank_recon_adjustments

Adjustment Types:
- bank_charge (Dr. Bank Charges / Cr. Bank)
- interest_income (Dr. Bank / Cr. Interest Income)
- service_fee (Dr. Service Fee / Cr. Bank)
- correction (Dr/Cr flexible based on over/under statement)
- other (Custom)
"""
from fastapi import APIRouter, Request, HTTPException
from database import get_db
from auth import require_auth, serialize_doc, log_activity
from datetime import datetime, timezone, date
from typing import Optional
import uuid
import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/rahaza/finance", tags=["rahaza-bank-recon"])

def _uid(): return str(uuid.uuid4())
def _now(): return datetime.now(timezone.utc)

ADJUSTMENT_TYPES = ["bank_charge", "interest_income", "service_fee", "correction", "other"]
ADJUSTMENT_STATUSES = ["draft", "posted"]


async def _require_fin(request: Request):
    user = await require_auth(request)
    role = (user.get("role") or "").lower()
    if role in ("superadmin", "admin", "owner", "accounting", "finance", "manager"):
        return user
    perms = user.get("_permissions") or []
    if "*" in perms or "finance.manage" in perms:
        return user
    raise HTTPException(403, "Forbidden: butuh permission finance")


# ─── CRUD ENDPOINTS ────────────────────────────────────────────────────────────

@router.get("/bank-recon-adjustments")
async def list_bank_adjustments(request: Request,
                                 bank_account_id: Optional[str] = None,
                                 adjustment_type: Optional[str] = None,
                                 status: Optional[str] = None,
                                 date_from: Optional[str] = None,
                                 date_to: Optional[str] = None):
    await _require_fin(request)
    db = get_db()
    
    q = {}
    if bank_account_id:
        q["bank_account_id"] = bank_account_id
    if adjustment_type:
        q["adjustment_type"] = adjustment_type
    if status:
        q["status"] = status
    if date_from:
        q["adjustment_date"] = {"$gte": date_from}
    if date_to:
        q.setdefault("adjustment_date", {})["$lte"] = date_to
    
    rows = await db.rahaza_bank_recon_adjustments.find(q, {"_id": 0}).sort("adjustment_date", -1).to_list(500)
    return serialize_doc(rows)


@router.post("/bank-recon-adjustments")
async def create_bank_adjustment(request: Request):
    user = await _require_fin(request)
    db = get_db()
    body = await request.json()
    
    bank_account_id = body.get("bank_account_id")
    adjustment_type = body.get("adjustment_type", "other")
    amount = float(body.get("amount", 0))
    
    if not bank_account_id:
        raise HTTPException(400, "bank_account_id wajib diisi")
    
    if amount <= 0:
        raise HTTPException(400, "amount harus > 0")
    
    if adjustment_type not in ADJUSTMENT_TYPES:
        raise HTTPException(400, f"Invalid adjustment_type. Must be one of: {', '.join(ADJUSTMENT_TYPES)}")
    
    # Validate bank account exists
    bank_account = await db.rahaza_cash_accounts.find_one({"id": bank_account_id}, {"_id": 0})
    if not bank_account:
        raise HTTPException(404, "Bank account tidak ditemukan")
    
    adjustment_date = body.get("adjustment_date", date.today().isoformat())
    
    doc = {
        "id": _uid(),
        "bank_account_id": bank_account_id,
        "bank_account_name": bank_account.get("name"),
        "bank_account_code": bank_account.get("gl_account_code") or "",  # H-06: jurnal ke akun bank rekening ini
        "adjustment_type": adjustment_type,
        "adjustment_date": adjustment_date,
        "amount": round(amount, 2),
        "description": body.get("description", ""),
        "reference_number": body.get("reference_number", ""),  # Bank statement ref
        "expense_account": body.get("expense_account", ""),  # Custom GL account (optional)
        "income_account": body.get("income_account", ""),    # Custom GL account (optional)
        "status": "draft",
        "posted_at": None,
        "posted_by": None,
        "je_id": None,
        "je_number": None,
        "notes": body.get("notes", ""),
        "created_at": _now(),
        "updated_at": _now(),
        "created_by": user.get("id"),
        "created_by_name": user.get("name", ""),
    }
    
    await db.rahaza_bank_recon_adjustments.insert_one(doc)
    await log_activity(user["id"], user.get("name", ""), "create", "bank_recon_adjustments",
                      f"Created {adjustment_type} adjustment for {bank_account.get('name')}: Rp {amount:,.0f}")
    
    return serialize_doc(doc)


@router.get("/bank-recon-adjustments/{adjustment_id}")
async def get_bank_adjustment(adjustment_id: str, request: Request):
    await _require_fin(request)
    db = get_db()
    
    doc = await db.rahaza_bank_recon_adjustments.find_one({"id": adjustment_id}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Adjustment not found")
    
    return serialize_doc(doc)


@router.put("/bank-recon-adjustments/{adjustment_id}")
async def update_bank_adjustment(adjustment_id: str, request: Request):
    await _require_fin(request)
    db = get_db()
    body = await request.json()
    
    existing = await db.rahaza_bank_recon_adjustments.find_one({"id": adjustment_id})
    if not existing:
        raise HTTPException(404, "Adjustment not found")
    
    if existing.get("status") != "draft":
        raise HTTPException(400, "Only draft adjustments can be updated")
    
    updates = {"updated_at": _now()}
    
    if "description" in body:
        updates["description"] = body["description"]
    if "amount" in body:
        updates["amount"] = round(float(body["amount"]), 2)
    if "adjustment_date" in body:
        updates["adjustment_date"] = body["adjustment_date"]
    if "reference_number" in body:
        updates["reference_number"] = body["reference_number"]
    if "expense_account" in body:
        updates["expense_account"] = body["expense_account"]
    if "income_account" in body:
        updates["income_account"] = body["income_account"]
    if "notes" in body:
        updates["notes"] = body["notes"]
    
    await db.rahaza_bank_recon_adjustments.update_one({"id": adjustment_id}, {"$set": updates})
    updated = await db.rahaza_bank_recon_adjustments.find_one({"id": adjustment_id}, {"_id": 0})
    
    return serialize_doc(updated)


@router.delete("/bank-recon-adjustments/{adjustment_id}")
async def delete_bank_adjustment(adjustment_id: str, request: Request):
    user = await _require_fin(request)
    db = get_db()
    
    existing = await db.rahaza_bank_recon_adjustments.find_one({"id": adjustment_id})
    if not existing:
        raise HTTPException(404, "Adjustment not found")
    
    if existing.get("status") != "draft":
        raise HTTPException(400, "Only draft adjustments can be deleted")
    
    await db.rahaza_bank_recon_adjustments.delete_one({"id": adjustment_id})
    await log_activity(user["id"], user.get("name", ""), "delete", "bank_recon_adjustments",
                      f"Deleted adjustment {existing.get('adjustment_type')} for {existing.get('adjustment_date')}")
    
    return {"ok": True, "message": "Adjustment deleted"}


# ─── POSTING ────────────────────────────────────────────────────────────────────

@router.post("/bank-recon-adjustments/{adjustment_id}/post")
async def post_bank_adjustment(adjustment_id: str, request: Request):
    """
    Post bank reconciliation adjustment ke GL.
    
    GL Mapping berdasarkan adjustment_type:
    - bank_charge: Dr. Bank Charges (6-2500) / Cr. Bank (1-1201)
    - interest_income: Dr. Bank (1-1201) / Cr. Interest Income (4-910)
    - service_fee: Dr. Service Fee (6-2501) / Cr. Bank (1-1201)
    - correction/other: Flexible based on expense_account/income_account
    """
    user = await _require_fin(request)
    db = get_db()
    
    adjustment = await db.rahaza_bank_recon_adjustments.find_one({"id": adjustment_id}, {"_id": 0})
    if not adjustment:
        raise HTTPException(404, "Adjustment not found")
    
    if adjustment.get("status") != "draft":
        raise HTTPException(400, f"Adjustment already {adjustment.get('status')}")
    
    # Post to GL
    try:
        from routes.rahaza_posting import post_bank_recon_adjustment
        posting_result = await post_bank_recon_adjustment(db, adjustment, user)
        
        if not posting_result.get("ok"):
            raise HTTPException(400, f"Posting failed: {posting_result.get('error')}")
        
        # Update status
        await db.rahaza_bank_recon_adjustments.update_one(
            {"id": adjustment_id},
            {"$set": {
                "status": "posted",
                "posted_at": _now(),
                "posted_by": user.get("id"),
                "je_id": posting_result.get("je_id"),
                "je_number": posting_result.get("je_number"),
            }}
        )
        
        # Update bank account balance + mutasi kas internal (H-05: kartu kas harus 1:1 dgn jurnal)
        bank_account_id = adjustment.get("bank_account_id")
        adjustment_type = adjustment.get("adjustment_type")
        amount = float(adjustment.get("amount", 0) or 0)
        if adjustment_type == "interest_income":
            direction = "in"
        elif adjustment_type in ("bank_charge", "service_fee"):
            direction = "out"
        elif adjustment.get("expense_account") and not adjustment.get("income_account"):
            direction = "out"
        elif adjustment.get("income_account") and not adjustment.get("expense_account"):
            direction = "in"
        else:
            direction = None  # custom Dr/Cr keduanya non-bank → saldo bank tidak berubah
        if direction:
            acc_doc = await db.rahaza_cash_accounts.find_one({"id": bank_account_id}, {"_id": 0, "name": 1})
            await db.rahaza_cash_accounts.update_one(
                {"id": bank_account_id}, {"$inc": {"balance": amount if direction == "in" else -amount}})
            await db.rahaza_cash_movements.insert_one({
                "id": _uid(), "account_id": bank_account_id, "account_name": (acc_doc or {}).get("name"),
                "direction": direction, "amount": round(amount, 2), "category": "bank_adjustment",
                "ref_id": adjustment_id, "ref_label": adjustment.get("description") or adjustment_type,
                "source_module": "bank_recon", "date": str(adjustment.get("adjustment_date") or "")[:10],
                "notes": adjustment_type, "timestamp": _now(),
                "created_by": user.get("id"), "created_by_name": user.get("name", ""),
                "gl_je_id": posting_result.get("je_id"), "gl_je_number": posting_result.get("je_number"),
                "gl_posted_at": _now()})
        
        await log_activity(user["id"], user.get("name", ""), "post_bank_adjustment", "bank_recon_adjustments",
                          f"Posted {adjustment_type} adjustment: JE {posting_result.get('je_number')}")
        
        updated = await db.rahaza_bank_recon_adjustments.find_one({"id": adjustment_id}, {"_id": 0})
        return serialize_doc(updated)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to post bank adjustment")
        raise HTTPException(500, str(e))
