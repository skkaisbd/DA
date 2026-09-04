"""invoice_edit_requests — Invoice Edit Approval workflow (SSOT-compatible).

Restores the backend for the live Finance-portal module `fin-approval`
("Persetujuan Invoice" / ApprovalModule.jsx) whose endpoints were removed when
routes/finance.py was deleted (Session #11.16 Phase D). Fixes BUG-FE-CONTRACT-3
(FE_BE_CONTRACT_AUDIT.md F3): FE called `/api/invoice-edit-requests[/{id}/approve|reject]`
→ 404.

Workflow:
  1. An admin creates an *edit request* (invoice is NOT mutated yet).
  2. Superadmin/Admin approves → after_snapshot is applied to the target invoice
     (whitelisted fields only) + change recorded to `invoice_change_history`.
  3. Or rejects → status Rejected (reason required).

Collections:
  - invoice_edit_requests   (the request queue)
  - invoice_change_history  (audit trail of applied changes)
Target invoice collections: rahaza_ar_invoices | rahaza_ap_invoices.
"""
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Request, HTTPException

from database import get_db
from auth import require_auth, serialize_doc, log_activity

router = APIRouter(prefix="/api/invoice-edit-requests", tags=["invoice-edit-requests"])

# Only these invoice fields may be changed via an approved edit request.
_ALLOWED_TARGET_COLLECTIONS = {"rahaza_ar_invoices", "rahaza_ap_invoices"}
_VALID_STATUS = {"Pending", "Approved", "Rejected"}


def _now():
    return datetime.now(timezone.utc)


def _uid():
    return str(uuid.uuid4())


def _to_num(v):
    """Best-effort float coercion; None on failure (never raises)."""
    try:
        if v is None or v == "":
            return None
        return float(v)
    except (TypeError, ValueError):
        return None


async def _require_approver(request: Request):
    """Approve/Reject permintaan ubah invoice.

    2026-08-06 — gerbang izin terpusat (fallback aman). Owner bisa memberi izin
    `fin.approval.manage` ke role keuangan tanpa menjadikannya admin.
    """
    from routes.shared import require_perm
    return await require_perm(
        request, "fin.approval.manage", "finance.approve",
        legacy_roles=("admin", "owner"),
        message="Akses ditolak: butuh izin approval perubahan invoice (fin.approval.manage).",
    )


def _build_change_summary(before: dict, after: dict) -> str:
    before = before or {}
    after = after or {}
    parts = []
    for key, label in (("total_amount", "Total"), ("discount", "Diskon"),
                       ("discount_amount", "Diskon"), ("notes", "Catatan"),
                       ("invoice_items", "Item")):
        if key in after and after.get(key) != before.get(key):
            parts.append(label)
    # de-dup while preserving order
    seen = []
    for p in parts:
        if p not in seen:
            seen.append(p)
    return ", ".join(f"Perubahan {p}" for p in seen) if seen else "Perubahan invoice"


# ──────────────────────────────────────────────────────────────────────────────
# LIST
# ──────────────────────────────────────────────────────────────────────────────
@router.get("")
async def list_requests(request: Request, status: Optional[str] = None, q: Optional[str] = None):
    await require_auth(request)
    db = get_db()
    query = {}
    if status and status in _VALID_STATUS:
        query["status"] = status
    if q:
        needle = str(q).strip()
        if needle:
            query["$or"] = [
                {"invoice_number": {"$regex": needle, "$options": "i"}},
                {"po_number": {"$regex": needle, "$options": "i"}},
                {"requested_by_name": {"$regex": needle, "$options": "i"}},
                {"requested_by": {"$regex": needle, "$options": "i"}},
            ]
    rows = await db.invoice_edit_requests.find(query, {"_id": 0}).sort("requested_at", -1).to_list(500)
    return serialize_doc(rows)


# ──────────────────────────────────────────────────────────────────────────────
# CREATE
# ──────────────────────────────────────────────────────────────────────────────
@router.post("")
async def create_request(request: Request):
    user = await require_auth(request)
    db = get_db()
    body = await request.json()
    if not isinstance(body, dict):
        raise HTTPException(400, "Body harus berupa objek JSON.")

    target_collection = body.get("target_collection")
    target_invoice_id = body.get("target_invoice_id") or body.get("invoice_id")
    after_snapshot = body.get("after_snapshot")
    if not isinstance(after_snapshot, dict) or not after_snapshot:
        raise HTTPException(400, "after_snapshot (objek perubahan) wajib diisi.")

    before_snapshot = body.get("before_snapshot") if isinstance(body.get("before_snapshot"), dict) else {}
    invoice_number = body.get("invoice_number") or ""
    po_number = body.get("po_number")
    invoice_category = body.get("invoice_category") or "CUSTOMER"

    # If a real target invoice is referenced, auto-fill before_snapshot from DB.
    if target_invoice_id and target_collection in _ALLOWED_TARGET_COLLECTIONS:
        inv = await db[target_collection].find_one({"id": target_invoice_id}, {"_id": 0})
        if not inv:
            raise HTTPException(404, "Invoice target tidak ditemukan.")
        invoice_number = invoice_number or inv.get("invoice_number") or ""
        po_number = po_number if po_number is not None else inv.get("po_number")
        before_snapshot = {
            "total_amount": inv.get("total"),
            "discount_amount": inv.get("discount_amount", 0),
            "notes": inv.get("notes", ""),
            "invoice_items": inv.get("items", []),
        }
        if invoice_category == "CUSTOMER" and target_collection == "rahaza_ap_invoices":
            invoice_category = "VENDOR"

    doc = {
        "id": _uid(),
        "status": "Pending",
        "invoice_number": invoice_number,
        "po_number": po_number,
        "invoice_category": invoice_category,
        "target_collection": target_collection if target_collection in _ALLOWED_TARGET_COLLECTIONS else None,
        "target_invoice_id": target_invoice_id,
        "before_snapshot": before_snapshot,
        "after_snapshot": after_snapshot,
        "change_summary": body.get("change_summary") or _build_change_summary(before_snapshot, after_snapshot),
        "requested_by": user.get("id"),
        "requested_by_name": user.get("name", ""),
        "requested_at": _now(),
        "approval_notes": None,
        "approved_by": None,
        "approved_by_name": None,
        "approved_at": None,
        "created_at": _now(),
        "updated_at": _now(),
    }
    await db.invoice_edit_requests.insert_one(doc)
    await log_activity(user.get("id"), user.get("name", ""), "create",
                       "invoice-edit-requests", f"Request edit invoice {invoice_number}")
    return serialize_doc(doc)


def _apply_after_snapshot_to_invoice(inv: dict, after: dict) -> dict:
    """Return a $set update dict applying only whitelisted, validated fields."""
    update = {}
    # notes
    if "notes" in after:
        update["notes"] = str(after.get("notes") or "")
    # discount (support both keys)
    disc = after.get("discount_amount", after.get("discount"))
    if disc is not None:
        d = _to_num(disc)
        if d is None or d < 0:
            raise HTTPException(400, "discount_amount tidak valid.")
        update["discount_amount"] = round(d)
    # invoice_items
    if "invoice_items" in after and isinstance(after.get("invoice_items"), list):
        update["items"] = after.get("invoice_items")
    elif "items" in after and isinstance(after.get("items"), list):
        update["items"] = after.get("items")
    # total_amount → total (+ recompute balance)
    if "total_amount" in after or "total" in after:
        t = _to_num(after.get("total_amount", after.get("total")))
        if t is None or t < 0:
            raise HTTPException(400, "total_amount tidak valid.")
        total = round(t)
        paid = _to_num(inv.get("paid_amount")) or 0
        update["total"] = total
        update["balance"] = max(0, round(total - paid))
    return update


# ──────────────────────────────────────────────────────────────────────────────
# APPROVE
# ──────────────────────────────────────────────────────────────────────────────
@router.put("/{req_id}/approve")
async def approve_request(req_id: str, request: Request):
    user = await _require_approver(request)
    db = get_db()
    try:
        body = await request.json()
    except Exception:
        body = {}
    approval_notes = (body or {}).get("approval_notes") or ""

    req = await db.invoice_edit_requests.find_one({"id": req_id}, {"_id": 0})
    if not req:
        raise HTTPException(404, "Request tidak ditemukan.")
    if req.get("status") != "Pending":
        raise HTTPException(400, f"Request sudah {req.get('status')}, tidak bisa di-approve lagi.")

    applied = {}
    target_collection = req.get("target_collection")
    target_invoice_id = req.get("target_invoice_id")
    if target_collection in _ALLOWED_TARGET_COLLECTIONS and target_invoice_id:
        inv = await db[target_collection].find_one({"id": target_invoice_id}, {"_id": 0})
        if not inv:
            raise HTTPException(404, "Invoice target sudah tidak ada, tidak bisa menerapkan perubahan.")
        applied = _apply_after_snapshot_to_invoice(inv, req.get("after_snapshot") or {})
        if applied:
            applied["updated_at"] = _now()
            await db[target_collection].update_one({"id": target_invoice_id}, {"$set": applied})

    now = _now()
    await db.invoice_edit_requests.update_one(
        {"id": req_id},
        {"$set": {
            "status": "Approved",
            "approval_notes": approval_notes,
            "approved_by": user.get("id"),
            "approved_by_name": user.get("name", ""),
            "approved_at": now,
            "updated_at": now,
        }},
    )
    # Audit trail
    await db.invoice_change_history.insert_one({
        "id": _uid(),
        "request_id": req_id,
        "invoice_number": req.get("invoice_number"),
        "target_collection": target_collection,
        "target_invoice_id": target_invoice_id,
        "action": "approved",
        "before_snapshot": req.get("before_snapshot"),
        "after_snapshot": req.get("after_snapshot"),
        "applied_fields": list(applied.keys()),
        "approval_notes": approval_notes,
        "approved_by": user.get("id"),
        "approved_by_name": user.get("name", ""),
        "approved_at": now,
    })
    await log_activity(user.get("id"), user.get("name", ""), "approve",
                       "invoice-edit-requests", f"Approve edit invoice {req.get('invoice_number')}")
    updated = await db.invoice_edit_requests.find_one({"id": req_id}, {"_id": 0})
    return serialize_doc({"message": "Request approved", "request": updated})


# ──────────────────────────────────────────────────────────────────────────────
# REJECT
# ──────────────────────────────────────────────────────────────────────────────
@router.put("/{req_id}/reject")
async def reject_request(req_id: str, request: Request):
    user = await _require_approver(request)
    db = get_db()
    try:
        body = await request.json()
    except Exception:
        body = {}
    approval_notes = ((body or {}).get("approval_notes") or "").strip()
    if not approval_notes:
        raise HTTPException(400, "Catatan/alasan reject wajib diisi.")

    req = await db.invoice_edit_requests.find_one({"id": req_id}, {"_id": 0})
    if not req:
        raise HTTPException(404, "Request tidak ditemukan.")
    if req.get("status") != "Pending":
        raise HTTPException(400, f"Request sudah {req.get('status')}, tidak bisa di-reject lagi.")

    now = _now()
    await db.invoice_edit_requests.update_one(
        {"id": req_id},
        {"$set": {
            "status": "Rejected",
            "approval_notes": approval_notes,
            "approved_by": user.get("id"),
            "approved_by_name": user.get("name", ""),
            "approved_at": now,
            "updated_at": now,
        }},
    )
    await log_activity(user.get("id"), user.get("name", ""), "reject",
                       "invoice-edit-requests", f"Reject edit invoice {req.get('invoice_number')}")
    updated = await db.invoice_edit_requests.find_one({"id": req_id}, {"_id": 0})
    return serialize_doc({"message": "Request rejected", "request": updated})
