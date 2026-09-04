"""
PT Rahaza — Finance Enhancement (Fase 8.5)

Scope (MVP):
  - Cost Centers: CRUD (dipakai tagging expense/HPP)
  - AR Invoices: draft -> sent -> partial_paid -> paid | overdue (manual check)
  - AP Invoices: draft -> sent -> partial_paid -> paid
  - Payments: record payment -> update AR/AP status otomatis
  - Cash Accounts: CRUD rekening kas/bank + saldo via movements ledger
  - Cash Movements: in/out, dilink ke AR payment, AP payment, expense
  - Expenses: entry biaya operasional (manual)
  - Aging Report AR: bucket 0-30, 31-60, 61-90, 90+
"""
from fastapi import APIRouter, Request, HTTPException, Depends
from routes.shared import require_portal_dep
from database import get_db
from utils.counters import gen_prefixed_number
from auth import require_auth, serialize_doc
from utils.data_quality import SkipTracker
from pymongo import ReturnDocument
import uuid
import logging
from datetime import datetime, timezone, date
from typing import Optional

logger = logging.getLogger(__name__)

from routes.rahaza_posting import (
    post_ar_invoice,
    post_ar_payment,
    post_ap_invoice,
    post_ap_payment,
    post_expense,
    void_ar_invoice_posting,
    void_ap_invoice_posting,
)

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/rahaza", tags=["rahaza-finance"],
                   dependencies=[Depends(require_portal_dep("finance"))])  # RBAC: portal finance (BUG-RBAC-1)

AR_STATUS = ["draft", "issued", "sent", "partial_paid", "paid", "overdue", "written_off", "cancelled"]
AP_STATUS = ["draft", "sent", "partial_paid", "paid", "cancelled"]


def _uid(): return str(uuid.uuid4())
def _now(): return datetime.now(timezone.utc)
def _today_iso(): return date.today().isoformat()


def _to_amount(v):
    """Coerce a payment amount to float; reject non-numeric input with 400 (not 500)."""
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        raise HTTPException(400, "amount harus berupa angka.")


def _to_num(v, field="nilai"):
    """Coerce optional numeric body field to float (default 0); reject non-numeric/NaN/inf → 400."""
    import math
    try:
        f = float(v or 0)
    except (TypeError, ValueError):
        raise HTTPException(400, f"{field} harus berupa angka.")
    if math.isnan(f) or math.isinf(f):
        raise HTTPException(400, f"{field} tidak valid (NaN/inf).")
    return f


def _norm_invoice_items(items, unit_default="pcs"):
    """Normalize & validate invoice line items.

    BUG-NUM-2/4 guard: qty & price WAJIB >= 0 (tolak negatif → total korup) dan numerik valid.
    Returns (subtotal, norm_items).
    """
    import math
    subtotal = 0.0
    norm = []
    for idx, it in enumerate(items or []):
        if not isinstance(it, dict):
            raise HTTPException(400, f"item ke-{idx + 1} tidak valid.")
        try:
            qty = float(it.get("qty") or it.get("quantity") or 0)
            price = float(it.get("price") or it.get("unit_price") or 0)
        except (TypeError, ValueError):
            raise HTTPException(400, f"qty/price item ke-{idx + 1} harus berupa angka.")
        if math.isnan(qty) or math.isinf(qty) or math.isnan(price) or math.isinf(price):
            raise HTTPException(400, f"qty/price item ke-{idx + 1} tidak valid (NaN/inf).")
        if qty < 0 or price < 0:
            raise HTTPException(400, f"qty/price item ke-{idx + 1} tidak boleh negatif.")
        amount = qty * price
        subtotal += amount
        norm.append({"description": it.get("description") or "", "qty": qty,
                     "unit": it.get("unit") or unit_default, "price": price, "amount": round(amount)})
    return subtotal, norm


def _validate_tax_discount(tax_pct, discount_amount, subtotal, tax):
    """BUG-NUM-2 guard: tax_pct & discount >= 0, dan discount <= subtotal+tax (total tak boleh negatif)."""
    if tax_pct < 0:
        raise HTTPException(400, "tax_pct tidak boleh negatif.")
    if discount_amount < 0:
        raise HTTPException(400, "discount_amount tidak boleh negatif.")
    if discount_amount > subtotal + tax + 0.01:
        raise HTTPException(400, "discount_amount melebihi subtotal + pajak (total invoice tidak boleh negatif).")


async def _require_fin(request: Request):
    user = await require_auth(request)
    role = (user.get("role") or "").lower()
    if role in ("superadmin", "admin", "owner", "accounting", "finance", "manager"):
        return user
    perms = user.get("_permissions") or []
    if "*" in perms or "finance.manage" in perms:
        return user
    raise HTTPException(403, "Forbidden: butuh permission finance.")


async def _gen_number(db, coll, prefix, requested: str = ""):
    """Nomor dokumen keuangan.

    FASE G (sesi #18): untuk jenis dokumen yang KEBIJAKANNYA sudah ditegakkan
    (`policy_enforced` di `data/doc_number_registry.py`) nomor lewat SATU pintu
    `core.doc_number_policy.issue_number` supaya mode OTOMATIS/MANUAL yang disetel
    System Admin benar-benar berlaku. Jenis lain tetap seperti sebelumnya —
    lebih baik jujur "belum ditegakkan" daripada menegakkan separuh jalan.
    """
    _POLICY_KEYS = {"rahaza_ar_invoices": "rahaza_ar_invoices.invoice_number"}
    key = _POLICY_KEYS.get(coll)
    if key:
        from core.doc_number_policy import issue_number
        return await issue_number(db, key, requested=(requested or "").strip())
    today = date.today().strftime("%Y%m%d")
    p = f"{prefix}-{today}-"
    # RC-5 fix: atomic race-safe numbering (was count_documents()+1)
    field = "invoice_number" if "invoice" in coll else "number"
    return await gen_prefixed_number(db, coll, field, p, 3)


# ── COST CENTERS ─────────────────────────────────────────────────────────────

@router.get("/cost-centers")
async def list_cost_centers(request: Request, active_only: bool = True):
    await require_auth(request)
    db = get_db()
    q = {"active": True} if active_only else {}
    rows = await db.rahaza_cost_centers.find(q, {"_id": 0}).sort("code", 1).to_list(500)
    return serialize_doc(rows)


@router.post("/cost-centers")
async def create_cost_center(request: Request):
    user = await _require_fin(request)
    db = get_db()
    body = await request.json()
    code = (body.get("code") or "").strip().upper()
    name = (body.get("name") or "").strip()
    if not code or not name:
        raise HTTPException(400, "code & name wajib.")
    if await db.rahaza_cost_centers.find_one({"code": code, "active": True}):
        raise HTTPException(409, f"Kode '{code}' sudah dipakai.")
    doc = {
        "id": _uid(), "code": code, "name": name,
        "category": body.get("category") or "umum",
        "overhead_rate_per_pcs": float(body.get("overhead_rate_per_pcs") or 0),
        "notes": body.get("notes") or "",
        "active": True,
        "created_at": _now(), "updated_at": _now(),
        "created_by": user["id"], "created_by_name": user.get("name", ""),
    }
    await db.rahaza_cost_centers.insert_one(doc)
    return serialize_doc(doc)


@router.put("/cost-centers/{cid}")
async def update_cost_center(cid: str, request: Request):
    await _require_fin(request)
    db = get_db()
    body = await request.json()
    body.pop("_id", None)
    body.pop("id", None)
    body.pop("created_at", None)
    body["updated_at"] = _now()
    res = await db.rahaza_cost_centers.update_one({"id": cid}, {"$set": body})
    if res.matched_count == 0:
        raise HTTPException(404, "Cost center tidak ditemukan.")
    out = await db.rahaza_cost_centers.find_one({"id": cid}, {"_id": 0})
    return serialize_doc(out)


@router.delete("/cost-centers/{cid}")
async def delete_cost_center(cid: str, request: Request):
    await _require_fin(request)
    db = get_db()
    res = await db.rahaza_cost_centers.update_one({"id": cid, "active": True}, {"$set": {"active": False, "updated_at": _now()}})
    if res.matched_count == 0:
        raise HTTPException(404, "Cost center tidak ditemukan.")
    return {"status": "deleted"}


# ── AR INVOICES ──────────────────────────────────────────────────────────────
@router.get("/ar-invoices")
async def list_ar(request: Request, status: Optional[str] = None, customer_id: Optional[str] = None):
    await require_auth(request)
    db = get_db()
    q = {}
    if status:
        q["status"] = status
    if customer_id:
        q["customer_id"] = customer_id
    rows = await db.rahaza_ar_invoices.find(q, {"_id": 0}).sort("issue_date", -1).to_list(500)
    # enrich customer
    cids = list({r.get("customer_id") for r in rows if r.get("customer_id")})
    cs = await db.rahaza_customers.find({"id": {"$in": cids}}, {"_id": 0}).to_list(500) if cids else []
    cmap = {c["id"]: c for c in cs}
    for r in rows:
        c = cmap.get(r.get("customer_id")) or {}
        r["customer_name"] = c.get("name")
    return serialize_doc(rows)


@router.post("/ar-invoices")
async def create_ar(request: Request):
    user = await _require_fin(request)
    db = get_db()
    body = await request.json()
    customer_id = body.get("customer_id")
    if not customer_id:
        raise HTTPException(400, "customer_id wajib.")
    customer = await db.rahaza_customers.find_one({"id": customer_id}, {"_id": 0})
    if not customer:
        raise HTTPException(404, "Customer tidak ditemukan.")
    items = body.get("items") or []
    subtotal, norm_items = _norm_invoice_items(items, unit_default="pcs")
    tax_pct = _to_num(body.get("tax_pct"), "tax_pct")
    tax = round(subtotal * tax_pct / 100)
    discount_amount = _to_num(body.get("discount_amount"), "discount_amount")  # Phase 9C
    _validate_tax_discount(tax_pct, discount_amount, subtotal, tax)
    total = round(subtotal + tax - discount_amount)
    invoice_number = await _gen_number(db, "rahaza_ar_invoices", "AR",
                                       requested=(body.get("invoice_number") or ""))
    doc = {
        "id": _uid(), "invoice_number": invoice_number,
        "customer_id": customer_id,
        "order_id": body.get("order_id") or None,
        "issue_date": body.get("issue_date") or _today_iso(),
        "due_date": body.get("due_date") or _today_iso(),
        "items": norm_items, "subtotal": round(subtotal), "tax_pct": tax_pct, "tax_amount": tax,
        "discount_amount": discount_amount,  # Phase 9C
        "total": total, "paid_amount": 0, "balance": total,
        "total_amount": total, "amount_paid": 0, "amount_due": total,  # skema kanonik (H-01)
        "status": "draft", "notes": body.get("notes") or "",
        "sales_channel": (body.get("sales_channel") or "").strip() or None,
        "created_at": _now(), "updated_at": _now(),
        "created_by": user["id"], "created_by_name": user.get("name", ""),
    }
    await db.rahaza_ar_invoices.insert_one(doc)
    return serialize_doc(doc)


@router.post("/ar-invoices/{iid}/status")
async def change_ar_status(iid: str, request: Request):
    user = await _require_fin(request)
    db = get_db()
    body = await request.json()
    new_status = (body.get("status") or "").lower()
    if new_status not in AR_STATUS:
        raise HTTPException(400, f"status invalid: {AR_STATUS}")
    inv = await db.rahaza_ar_invoices.find_one({"id": iid}, {"_id": 0})
    if not inv:
        raise HTTPException(404, "Invoice tidak ditemukan.")
    old_status = inv.get("status")
    if new_status == "sent":
        new_status = "issued"   # kanonik (H-01)
    await db.rahaza_ar_invoices.update_one({"id": iid}, {"$set": {"status": new_status, "updated_at": _now()}})
    out = await db.rahaza_ar_invoices.find_one({"id": iid}, {"_id": 0})

    # ── F2 Auto-post hook ────────────────────────────────────────────────────
    posting_result = None
    try:
        if new_status == "issued" and old_status not in ("issued", "sent") and not out.get("gl_je_id"):
            posting_result = await post_ar_invoice(db, out, user)
        elif new_status == "cancelled" and out.get("gl_je_id"):
            posting_result = await void_ar_invoice_posting(db, iid, user, reason="AR cancelled")
    except Exception as e:
        log.exception("AR auto-post failed")
        posting_result = {"ok": False, "error": str(e)}

    # refresh after posting (posting may have updated gl_* fields)
    out = await db.rahaza_ar_invoices.find_one({"id": iid}, {"_id": 0})
    if posting_result is not None:
        out["_posting_result"] = posting_result
    return serialize_doc(out)


@router.post("/ar-invoices/{iid}/send")
async def send_ar_invoice(iid: str, request: Request):
    """F2: explicit 'send' action → status=sent + auto-post JE."""
    user = await _require_fin(request)
    db = get_db()
    inv = await db.rahaza_ar_invoices.find_one({"id": iid}, {"_id": 0})
    if not inv:
        raise HTTPException(404, "Invoice tidak ditemukan.")
    if inv.get("status") not in ("draft", "sent", "issued"):
        raise HTTPException(400, f"Hanya draft/issued yang bisa di-send. Status: {inv.get('status')}")
    await db.rahaza_ar_invoices.update_one({"id": iid}, {"$set": {"status": "issued", "updated_at": _now()}})
    out = await db.rahaza_ar_invoices.find_one({"id": iid}, {"_id": 0})
    posting_result = None
    try:
        posting_result = await post_ar_invoice(db, out, user)
    except Exception as e:
        log.exception("AR send auto-post failed")
        posting_result = {"ok": False, "error": str(e)}
    out = await db.rahaza_ar_invoices.find_one({"id": iid}, {"_id": 0})
    out["_posting_result"] = posting_result
    return serialize_doc(out)


@router.post("/ar-invoices/{iid}/post-to-gl")
async def retry_post_ar(iid: str, request: Request):
    """F2: manual retry posting AR invoice to GL (idempotent)."""
    user = await _require_fin(request)
    db = get_db()
    inv = await db.rahaza_ar_invoices.find_one({"id": iid}, {"_id": 0})
    if not inv:
        raise HTTPException(404, "Invoice tidak ditemukan.")
    result = await post_ar_invoice(db, inv, user)
    out = await db.rahaza_ar_invoices.find_one({"id": iid}, {"_id": 0})
    out["_posting_result"] = result
    return serialize_doc(out)


@router.post("/ar-invoices/{iid}/payment")
async def record_ar_payment(iid: str, request: Request):
    user = await _require_fin(request)
    db = get_db()
    body = await request.json()
    amount = _to_amount(body.get("amount"))
    if amount <= 0:
        raise HTTPException(400, "amount harus > 0")
    inv = await db.rahaza_ar_invoices.find_one({"id": iid}, {"_id": 0})
    if not inv:
        raise HTTPException(404, "Invoice tidak ditemukan.")
    # ── R10 concurrency hardening (TOCTOU-safe): state-check + overpay guard live
    # INSIDE the filter; paid/balance/status recomputed atomically via aggregation
    # pipeline. Prevents lost-update & overpay under parallel requests (CC3).
    updated = await db.rahaza_ar_invoices.find_one_and_update(
        {
            "id": iid,
            "status": {"$nin": ["cancelled", "void", "written_off"]},
            "$expr": {"$lte": [
                {"$add": [{"$ifNull": ["$paid_amount", 0]}, amount]},
                {"$add": [{"$ifNull": ["$total", 0]}, 0.01]},
            ]},
        },
        [{"$set": {
            "paid_amount": {"$round": [{"$add": [{"$ifNull": ["$paid_amount", 0]}, amount]}, 0]},
            "balance": {"$max": [0, {"$round": [
                {"$subtract": [{"$ifNull": ["$total", 0]},
                               {"$add": [{"$ifNull": ["$paid_amount", 0]}, amount]}]}, 0]}]},
            "status": {"$cond": [
                {"$gte": [{"$add": [{"$ifNull": ["$paid_amount", 0]}, amount]},
                          {"$subtract": [{"$ifNull": ["$total", 0]}, 0.01]}]},
                "paid", "partial_paid"]},
            "updated_at": _now(),
        }},
         # cermin kanonik (H-01)
         {"$set": {"total_amount": {"$ifNull": ["$total", 0]}, "amount_paid": "$paid_amount", "amount_due": "$balance"}}],
        return_document=ReturnDocument.AFTER,
    )
    if not updated:
        # No write happened — re-read to return the precise 404/400 reason.
        inv2 = await db.rahaza_ar_invoices.find_one({"id": iid}, {"_id": 0})
        if not inv2:
            raise HTTPException(404, "Invoice tidak ditemukan.")
        _st = (inv2.get("status") or "").lower()
        if _st in ("cancelled", "void", "written_off"):
            raise HTTPException(400, f"Tidak bisa mencatat pembayaran untuk invoice berstatus '{_st}'.")
        _total = float(inv2.get("total") or 0)
        _prev = float(inv2.get("paid_amount") or 0)
        raise HTTPException(400, f"Pembayaran melebihi total invoice (balance: {_total - _prev:.0f})")
    inv = updated
    # Record cash movement
    account_id = body.get("account_id")
    payment_date = body.get("date") or _today_iso()
    movement_id = None
    if account_id:
        acc = await db.rahaza_cash_accounts.find_one({"id": account_id}, {"_id": 0})
        if acc:
            movement_id = _uid()
            await db.rahaza_cash_movements.insert_one({
                "id": movement_id, "account_id": account_id, "account_name": acc.get("name"),
                "direction": "in", "amount": round(amount),
                "category": "ar_payment", "ref_id": iid, "ref_label": inv.get("invoice_number"),
                "date": payment_date, "notes": body.get("notes") or "",
                "timestamp": _now(), "created_by": user["id"], "created_by_name": user.get("name", ""),
            })
            await db.rahaza_cash_accounts.update_one({"id": account_id}, {"$inc": {"balance": round(amount)}})

    # ── F2 Auto-post: ensure AR invoice posted first (if not), then post payment receipt
    posting_result = None
    try:
        inv_refresh = await db.rahaza_ar_invoices.find_one({"id": iid}, {"_id": 0})
        if not inv_refresh.get("gl_je_id"):
            await post_ar_invoice(db, inv_refresh, user)
            inv_refresh = await db.rahaza_ar_invoices.find_one({"id": iid}, {"_id": 0})
        posting_result = await post_ar_payment(
            db, inv_refresh, amount, account_id, payment_date, user, movement_id=movement_id
        )
    except Exception as e:
        log.exception("AR payment auto-post failed")
        posting_result = {"ok": False, "error": str(e)}

    out = await db.rahaza_ar_invoices.find_one({"id": iid}, {"_id": 0})
    out["_posting_result"] = posting_result
    out["_movement_id"] = movement_id
    return serialize_doc(out)


# 2026-08-07 — DI SINI DULU ADA DEKORATOR MENGGANTUNG: `@router.get("/ar-aging")`
# berdiri sendiri tanpa fungsi di bawahnya. Python MENUMPUK dekorator yang
# terpisah baris kosong/komentar, jadi dekorator itu menempel ke
# `write_off_bad_debt` di bawah. Akibatnya DUA hal serius:
#   1. `GET /api/rahaza/ar-aging` sebenarnya memanggil **write-off piutang macet**
#      — sebuah operasi yang MEMPOSTING JURNAL GL (Dr Beban Piutang Macet /
#      Cr Piutang) lewat metode GET; dan karena path `/ar-aging` tak punya
#      `{iid}`, FastAPI menjadikan `iid` sebagai query parameter wajib (itulah
#      sebabnya endpoint ini "minta iid" dan tampak rusak).
#   2. Fungsi `ar_aging()` yang sesungguhnya TIDAK PERNAH terdaftar ⇒ laporan
#      aging AR adalah KODE MATI selama ini.
# Dekoratornya sekarang dipindahkan ke fungsi `ar_aging()` yang benar (lihat di
# bawah). Gate `verify_unreachable_code` tidak menangkap pola ini — dekorator
# menggantung yang dipisahkan baris kosong + komentar adalah titik butanya.


# ══════════════════════════════════════════════════════════════════════════════
# PHASE 9A: BAD DEBT WRITE-OFF
# ══════════════════════════════════════════════════════════════════════════════
@router.post("/ar-invoices/{iid}/write-off-bad-debt")
async def write_off_bad_debt(iid: str, request: Request):
    """
    Phase 9A: Write off AR invoice as bad debt.
    
    Requirements:
    - Invoice status must be 'overdue' or 'sent'
    - Auto-post GL: Dr. Bad Debt Expense (6-2600) / Cr. AR (1-1301)
    - Update invoice status to 'written_off'
    - Record balance at write-off date
    
    Body:
    {
        "reason": "Customer bangkrut / tidak tertagih > 180 hari",
        "write_off_date": "2026-06-01"  // Optional, default: today
    }
    """
    user = await _require_fin(request)
    db = get_db()
    body = await request.json()
    
    inv = await db.rahaza_ar_invoices.find_one({"id": iid}, {"_id": 0})
    if not inv:
        raise HTTPException(404, "Invoice tidak ditemukan")
    
    current_status = inv.get("status")
    if current_status in ("written_off", "cancelled", "paid"):
        raise HTTPException(400, f"Invoice dengan status '{current_status}' tidak bisa di-write off")
    
    balance = float(inv.get("balance") or 0)
    if balance <= 0:
        raise HTTPException(400, "Invoice sudah lunas, tidak bisa di-write off")
    
    write_off_date = body.get("write_off_date") or _today_iso()
    reason = body.get("reason", "").strip()
    
    if not reason:
        raise HTTPException(400, "Reason wajib diisi untuk audit trail")
    
    # Update invoice status
    await db.rahaza_ar_invoices.update_one(
        {"id": iid},
        {"$set": {
            "status": "written_off",
            "write_off_date": write_off_date,
            "write_off_reason": reason,
            "write_off_amount": round(balance, 2),
            "amount_due": 0, "balance": 0,
            "write_off_by": user.get("id"),
            "write_off_by_name": user.get("name", ""),
            "write_off_at": _now(),
            "updated_at": _now(),
        }}
    )
    
    # Auto-post bad debt expense
    posting_result = None
    try:
        from routes.rahaza_posting import post_bad_debt_writeoff
        inv_refresh = await db.rahaza_ar_invoices.find_one({"id": iid}, {"_id": 0})
        posting_result = await post_bad_debt_writeoff(db, inv_refresh, user)
    except Exception as e:
        log.exception("Bad debt write-off GL posting failed")
        posting_result = {"ok": False, "error": str(e)}
    
    # Get final state
    out = await db.rahaza_ar_invoices.find_one({"id": iid}, {"_id": 0})
    out["_posting_result"] = posting_result
    
    from auth import log_activity
    await log_activity(
        user.get("id", "system"),
        user.get("name", "system"),
        "write_off_bad_debt",
        "ar_invoices",
        f"Write-off bad debt: {inv.get('invoice_number')} - Rp {balance:,.0f} - Reason: {reason}"
    )
    
    return serialize_doc(out)


@router.get("/ar-invoices/overdue-report")
async def get_overdue_ar_report(request: Request, days: int = 30):
    """
    Phase 9A: Get overdue AR invoices untuk bad debt review.
    
    Query params:
    - days: minimum overdue days (default: 30)
    
    Returns: List of overdue invoices sorted by overdue days (oldest first)
    """
    await _require_fin(request)
    db = get_db()
    
    today = date.today()
    
    # Get all sent/overdue/partial_paid invoices with balance > 0
    query = {
        "status": {"$in": ["sent", "issued", "overdue", "partial_paid"]},
        "balance": {"$gt": 0}
    }
    
    invoices = await db.rahaza_ar_invoices.find(query, {"_id": 0}).to_list(1000)
    
    # 2026-08-07 — DULU invoice yang `due_date`-nya kosong/rusak di-`continue`
    # DIAM-DIAM. Akibatnya invoice itu HILANG dari daftar jatuh tempo: tidak ada
    # yang menagih, dan `total_overdue_amount` tetap tampak wajar sehingga tak ada
    # yang curiga. Sekarang setiap baris yang dilewati dicatat + dikembalikan ke
    # layar lewat `data_quality` supaya bisa diperbaiki.
    dq = SkipTracker("daftar AR jatuh tempo")
    overdue_list = []
    for inv in invoices:
        due_date_str = inv.get("due_date")
        if not due_date_str:
            dq.skip(doc_id=inv.get("id"), label=inv.get("invoice_number"),
                    field="due_date", value=due_date_str,
                    reason="tanggal jatuh tempo kosong")
            continue
        
        try:
            due_date = date.fromisoformat(due_date_str[:10])
            overdue_days = (today - due_date).days
            
            if overdue_days >= days:
                overdue_list.append({
                    "id": inv.get("id"),
                    "invoice_number": inv.get("invoice_number"),
                    "customer_id": inv.get("customer_id"),
                    "issue_date": inv.get("issue_date"),
                    "due_date": due_date_str,
                    "overdue_days": overdue_days,
                    "total": inv.get("total"),
                    "paid_amount": inv.get("paid_amount"),
                    "balance": inv.get("balance"),
                    "status": inv.get("status"),
                    "aging_bucket": (
                        "0-30 days" if overdue_days <= 30 else
                        "31-60 days" if overdue_days <= 60 else
                        "61-90 days" if overdue_days <= 90 else
                        "91-180 days" if overdue_days <= 180 else
                        ">180 days (bad debt candidate)"
                    )
                })
        except (ValueError, TypeError) as e:
            dq.skip(doc_id=inv.get("id"), label=inv.get("invoice_number"),
                    field="due_date", value=due_date_str, error=e)
            continue
    dq.log(logger)
    
    # Sort by overdue_days (oldest first)
    overdue_list.sort(key=lambda x: x["overdue_days"], reverse=True)
    
    # Calculate summary
    total_overdue = sum(inv["balance"] for inv in overdue_list)
    count_high_risk = sum(1 for inv in overdue_list if inv["overdue_days"] > 180)
    
    return serialize_doc({
        "summary": {
            "total_overdue_invoices": len(overdue_list),
            "total_overdue_amount": round(total_overdue, 2),
            "high_risk_count": count_high_risk,
            "high_risk_amount": round(sum(inv["balance"] for inv in overdue_list if inv["overdue_days"] > 180), 2),
        },
        "invoices": overdue_list,
        "data_quality": dq.as_dict(),
    })

@router.get("/ar-aging")
async def ar_aging(request: Request, source: Optional[str] = None):
    """Aging piutang TUNGGAL (internal + maklon) — skema kanonik (H-01). ?source=internal|maklon."""
    await require_auth(request)
    db = get_db()
    from routes.rahaza_ar_canonical import compute_ar_aging
    res = await compute_ar_aging(db, source=source or None)
    return {"buckets": {k: round(v) for k, v in res["buckets"].items()}, "total": round(res["total"]),
            "count": res["count"], "details": serialize_doc(res["rows"]), "data_quality": res["data_quality"]}


# ── AP INVOICES ──────────────────────────────────────────────────────────────
@router.get("/ap-invoices")
async def list_ap(request: Request, status: Optional[str] = None):
    await require_auth(request)
    db = get_db()
    q = {}
    if status:
        q["status"] = status
    rows = await db.rahaza_ap_invoices.find(q, {"_id": 0}).sort("issue_date", -1).to_list(500)
    return serialize_doc(rows)


@router.post("/ap-invoices")
async def create_ap(request: Request):
    user = await _require_fin(request)
    db = get_db()
    body = await request.json()
    vendor_name = (body.get("vendor_name") or "").strip()
    if not vendor_name:
        raise HTTPException(400, "vendor_name wajib.")
    items = body.get("items") or []
    subtotal, norm = _norm_invoice_items(items, unit_default="")
    tax_pct = _to_num(body.get("tax_pct"), "tax_pct")
    if tax_pct < 0:
        raise HTTPException(400, "tax_pct tidak boleh negatif.")
    tax = round(subtotal * tax_pct / 100)
    total = round(subtotal + tax)
    invoice_number = await _gen_number(db, "rahaza_ap_invoices", "AP")
    doc = {
        "id": _uid(), "invoice_number": invoice_number,
        "vendor_name": vendor_name, "vendor_code": body.get("vendor_code") or "",
        "issue_date": body.get("issue_date") or _today_iso(),
        "due_date": body.get("due_date") or _today_iso(),
        "items": norm, "subtotal": round(subtotal), "tax_pct": tax_pct, "tax_amount": tax,
        "total": total, "paid_amount": 0, "balance": total,
        "status": "draft", "notes": body.get("notes") or "",
        "cost_center_id": body.get("cost_center_id") or None,
        "created_at": _now(), "updated_at": _now(),
        "created_by": user["id"], "created_by_name": user.get("name", ""),
    }
    await db.rahaza_ap_invoices.insert_one(doc)
    return serialize_doc(doc)


@router.post("/ap-invoices/{iid}/payment")
async def record_ap_payment(iid: str, request: Request):
    user = await _require_fin(request)
    db = get_db()
    body = await request.json()
    amount = _to_amount(body.get("amount"))
    if amount <= 0:
        raise HTTPException(400, "amount harus > 0")
    inv = await db.rahaza_ap_invoices.find_one({"id": iid}, {"_id": 0})
    if not inv:
        raise HTTPException(404, "Invoice tidak ditemukan.")
    # ── R10 concurrency hardening (TOCTOU-safe): atomic conditional payment (CC3).
    updated = await db.rahaza_ap_invoices.find_one_and_update(
        {
            "id": iid,
            "status": {"$nin": ["cancelled", "void", "written_off"]},
            "$expr": {"$lte": [
                {"$add": [{"$ifNull": ["$paid_amount", 0]}, amount]},
                {"$add": [{"$ifNull": ["$total", 0]}, 0.01]},
            ]},
        },
        [{"$set": {
            "paid_amount": {"$round": [{"$add": [{"$ifNull": ["$paid_amount", 0]}, amount]}, 0]},
            "balance": {"$max": [0, {"$round": [
                {"$subtract": [{"$ifNull": ["$total", 0]},
                               {"$add": [{"$ifNull": ["$paid_amount", 0]}, amount]}]}, 0]}]},
            "status": {"$cond": [
                {"$gte": [{"$add": [{"$ifNull": ["$paid_amount", 0]}, amount]},
                          {"$subtract": [{"$ifNull": ["$total", 0]}, 0.01]}]},
                "paid", "partial_paid"]},
            "updated_at": _now(),
        }}],
        return_document=ReturnDocument.AFTER,
    )
    if not updated:
        inv2 = await db.rahaza_ap_invoices.find_one({"id": iid}, {"_id": 0})
        if not inv2:
            raise HTTPException(404, "Invoice tidak ditemukan.")
        _st = (inv2.get("status") or "").lower()
        if _st in ("cancelled", "void", "written_off"):
            raise HTTPException(400, f"Tidak bisa mencatat pembayaran untuk invoice berstatus '{_st}'.")
        raise HTTPException(400, "Pembayaran melebihi total invoice.")
    inv = updated
    account_id = body.get("account_id")
    payment_date = body.get("date") or _today_iso()
    movement_id = None
    if account_id:
        acc = await db.rahaza_cash_accounts.find_one({"id": account_id}, {"_id": 0})
        if acc:
            movement_id = _uid()
            await db.rahaza_cash_movements.insert_one({
                "id": movement_id, "account_id": account_id, "account_name": acc.get("name"),
                "direction": "out", "amount": round(amount),
                "category": "ap_payment", "ref_id": iid, "ref_label": inv.get("invoice_number"),
                "date": payment_date, "notes": body.get("notes") or "",
                "timestamp": _now(), "created_by": user["id"], "created_by_name": user.get("name", ""),
            })
            await db.rahaza_cash_accounts.update_one({"id": account_id}, {"$inc": {"balance": -round(amount)}})

    # ── F2 Auto-post: ensure AP invoice posted first, then post payment disbursement
    posting_result = None
    try:
        inv_refresh = await db.rahaza_ap_invoices.find_one({"id": iid}, {"_id": 0})
        if not inv_refresh.get("gl_je_id"):
            await post_ap_invoice(db, inv_refresh, user)
            inv_refresh = await db.rahaza_ap_invoices.find_one({"id": iid}, {"_id": 0})
        posting_result = await post_ap_payment(
            db, inv_refresh, amount, account_id, payment_date, user, movement_id=movement_id
        )
    except Exception as e:
        log.exception("AP payment auto-post failed")
        posting_result = {"ok": False, "error": str(e)}

    out = await db.rahaza_ap_invoices.find_one({"id": iid}, {"_id": 0})
    out["_posting_result"] = posting_result
    out["_movement_id"] = movement_id
    return serialize_doc(out)


@router.post("/ap-invoices/{iid}/status")
async def change_ap_status(iid: str, request: Request):
    """F2: AP status change (draft → sent → cancelled). Auto-post JE on sent."""
    user = await _require_fin(request)
    db = get_db()
    body = await request.json()
    new_status = (body.get("status") or "").lower()
    if new_status not in AP_STATUS:
        raise HTTPException(400, f"status invalid: {AP_STATUS}")
    inv = await db.rahaza_ap_invoices.find_one({"id": iid}, {"_id": 0})
    if not inv:
        raise HTTPException(404, "Invoice tidak ditemukan.")
    old_status = inv.get("status")
    await db.rahaza_ap_invoices.update_one({"id": iid}, {"$set": {"status": new_status, "updated_at": _now()}})
    out = await db.rahaza_ap_invoices.find_one({"id": iid}, {"_id": 0})

    posting_result = None
    try:
        if new_status == "sent" and old_status != "sent" and not out.get("gl_je_id"):
            posting_result = await post_ap_invoice(db, out, user)
        elif new_status == "cancelled" and out.get("gl_je_id"):
            posting_result = await void_ap_invoice_posting(db, iid, user, reason="AP cancelled")
    except Exception as e:
        log.exception("AP auto-post failed")
        posting_result = {"ok": False, "error": str(e)}

    out = await db.rahaza_ap_invoices.find_one({"id": iid}, {"_id": 0})
    if posting_result is not None:
        out["_posting_result"] = posting_result
    return serialize_doc(out)


@router.post("/ap-invoices/{iid}/send")
async def send_ap_invoice(iid: str, request: Request):
    """F2: explicit 'send' action → status=sent + auto-post JE."""
    user = await _require_fin(request)
    db = get_db()
    inv = await db.rahaza_ap_invoices.find_one({"id": iid}, {"_id": 0})
    if not inv:
        raise HTTPException(404, "Invoice tidak ditemukan.")
    if inv.get("status") not in ("draft", "sent"):
        raise HTTPException(400, f"Hanya draft/sent yang bisa di-send. Status: {inv.get('status')}")
    await db.rahaza_ap_invoices.update_one({"id": iid}, {"$set": {"status": "sent", "updated_at": _now()}})
    out = await db.rahaza_ap_invoices.find_one({"id": iid}, {"_id": 0})
    posting_result = None
    try:
        posting_result = await post_ap_invoice(db, out, user)
    except Exception as e:
        log.exception("AP send auto-post failed")
        posting_result = {"ok": False, "error": str(e)}
    out = await db.rahaza_ap_invoices.find_one({"id": iid}, {"_id": 0})
    out["_posting_result"] = posting_result
    return serialize_doc(out)


@router.post("/ap-invoices/{iid}/post-to-gl")
async def retry_post_ap(iid: str, request: Request):
    """F2: manual retry posting AP invoice to GL (idempotent)."""
    user = await _require_fin(request)
    db = get_db()
    inv = await db.rahaza_ap_invoices.find_one({"id": iid}, {"_id": 0})
    if not inv:
        raise HTTPException(404, "Invoice tidak ditemukan.")
    result = await post_ap_invoice(db, inv, user)
    out = await db.rahaza_ap_invoices.find_one({"id": iid}, {"_id": 0})
    out["_posting_result"] = result
    return serialize_doc(out)


@router.get("/ap-aging")
async def ap_aging(request: Request):
    """F2: AP Aging report (bucket 0, 1-30, 31-60, 61-90, 90+)."""
    await require_auth(request)
    db = get_db()
    today = date.today()
    rows = await db.rahaza_ap_invoices.find(
        {"status": {"$in": ["sent", "partial_paid"]}}, {"_id": 0}
    ).to_list(500)
    buckets = {"current": 0, "1_30": 0, "31_60": 0, "61_90": 0, "90_plus": 0}
    details = []
    for r in rows:
        try:
            due = datetime.strptime(r["due_date"], "%Y-%m-%d").date()
            days_overdue = (today - due).days
        except Exception:
            days_overdue = 0
        balance = float(r.get("balance") or 0)
        if days_overdue <= 0:
            buckets["current"] += balance
        elif days_overdue <= 30:
            buckets["1_30"] += balance
        elif days_overdue <= 60:
            buckets["31_60"] += balance
        elif days_overdue <= 90:
            buckets["61_90"] += balance
        else:
            buckets["90_plus"] += balance
        details.append({**r, "days_overdue": days_overdue})
    return {
        "buckets": {k: round(v) for k, v in buckets.items()},
        "total": round(sum(buckets.values())),
        "details": serialize_doc(details),
    }


# ── CASH ACCOUNTS & MOVEMENTS ────────────────────────────────────────────────
@router.get("/cash-accounts")
async def list_cash_accounts(request: Request, active_only: bool = True):
    await require_auth(request)
    db = get_db()
    q = {"active": True} if active_only else {}
    rows = await db.rahaza_cash_accounts.find(q, {"_id": 0}).sort("code", 1).to_list(500)
    return serialize_doc(rows)


@router.post("/cash-accounts")
async def create_cash_account(request: Request):
    user = await _require_fin(request)
    db = get_db()
    body = await request.json()
    code = (body.get("code") or "").strip().upper()
    name = (body.get("name") or "").strip()
    if not code or not name:
        raise HTTPException(400, "code & name wajib.")
    if await db.rahaza_cash_accounts.find_one({"code": code, "active": True}):
        raise HTTPException(409, f"Kode '{code}' sudah terpakai.")
    doc = {
        "id": _uid(), "code": code, "name": name,
        "type": body.get("type") or "cash",  # cash | bank
        "bank_name": body.get("bank_name") or "",
        "account_number": body.get("account_number") or "",
        "balance": float(body.get("opening_balance") or 0),
        "opening_balance": float(body.get("opening_balance") or 0),
        "notes": body.get("notes") or "",
        "active": True,
        "created_at": _now(), "updated_at": _now(),
    }
    await db.rahaza_cash_accounts.insert_one(doc)
    # Phase 6: auto-create COA subledger (Bank) — idempotent, non-fatal.
    # 2026-08-07 — DULU `except Exception: pass`. Rekening bank tanpa subledger
    # COA berarti mutasi kasnya tidak punya tempat di Buku Besar; ini ketahuan
    # jauh kemudian saat neraca tidak seimbang. Tetap non-fatal (pembuatan
    # rekening tidak boleh gagal karena COA), tapi WAJIB tercatat.
    try:
        from routes.coa_auto import ensure_subledger_for_entity
        await ensure_subledger_for_entity(db, "bank", doc, user)
    except Exception as e:  # noqa: BLE001
        log.error("[coa] subledger COA bank GAGAL dibuat untuk rekening %s (%s) — "
                  "mutasi kas rekening ini tidak punya akun Buku Besar: %s",
                  doc.get("name") or doc.get("id"), doc.get("account_number"), e)
    out = await db.rahaza_cash_accounts.find_one({"id": doc["id"]}, {"_id": 0})
    return serialize_doc(out)


@router.put("/cash-accounts/{aid}")
async def update_cash_account(aid: str, request: Request):
    await _require_fin(request)
    db = get_db()
    body = await request.json()
    body.pop("_id", None)
    body.pop("id", None)
    body.pop("created_at", None)
    body.pop("balance", None)
    body["updated_at"] = _now()
    await db.rahaza_cash_accounts.update_one({"id": aid}, {"$set": body})
    return {"status": "ok"}


@router.delete("/cash-accounts/{aid}")
async def delete_cash_account(aid: str, request: Request):
    await _require_fin(request)
    db = get_db()
    await db.rahaza_cash_accounts.update_one({"id": aid, "active": True}, {"$set": {"active": False}})
    return {"status": "deleted"}


@router.get("/cash-movements")
async def list_movements(request: Request, account_id: Optional[str] = None, from_: Optional[str] = None, to: Optional[str] = None):
    await require_auth(request)
    db = get_db()
    q = {}
    if account_id:
        q["account_id"] = account_id
    if from_ or to:
        rg = {}
        if from_:
            rg["$gte"] = from_
        if to:
            rg["$lte"] = to
        q["date"] = rg
    rows = await db.rahaza_cash_movements.find(q, {"_id": 0}).sort("timestamp", -1).to_list(500)
    return serialize_doc(rows)


# ── EXPENSES ─────────────────────────────────────────────────────────────────
@router.get("/expenses")
async def list_expenses(request: Request, from_: Optional[str] = None, to: Optional[str] = None, cost_center_id: Optional[str] = None):
    await require_auth(request)
    db = get_db()
    q = {}
    if cost_center_id:
        q["cost_center_id"] = cost_center_id
    if from_ or to:
        rg = {}
        if from_:
            rg["$gte"] = from_
        if to:
            rg["$lte"] = to
        q["date"] = rg
    rows = await db.rahaza_expenses.find(q, {"_id": 0}).sort("date", -1).to_list(500)
    # enrich cost center
    ccids = list({r.get("cost_center_id") for r in rows if r.get("cost_center_id")})
    ccs = await db.rahaza_cost_centers.find({"id": {"$in": ccids}}, {"_id": 0}).to_list(500) if ccids else []
    ccmap = {c["id"]: c for c in ccs}
    for r in rows:
        cc = ccmap.get(r.get("cost_center_id")) or {}
        r["cost_center_code"] = cc.get("code")
        r["cost_center_name"] = cc.get("name")
    return serialize_doc(rows)


@router.post("/expenses")
async def create_expense(request: Request):
    user = await _require_fin(request)
    db = get_db()
    body = await request.json()
    amount = _to_amount(body.get("amount"))
    if amount <= 0:
        raise HTTPException(400, "amount harus > 0")
    doc = {
        "id": _uid(),
        "date": body.get("date") or _today_iso(),
        "category": body.get("category") or "operasional",
        "description": body.get("description") or "",
        "amount": round(amount),
        "cost_center_id": body.get("cost_center_id") or None,
        "account_id": body.get("account_id") or None,
        "gl_debit_code": body.get("gl_debit_code") or None,  # F2: optional override
        "notes": body.get("notes") or "",
        "created_at": _now(), "created_by": user["id"], "created_by_name": user.get("name", ""),
    }
    await db.rahaza_expenses.insert_one(doc)
    # If account_id provided, record cash movement
    if doc["account_id"]:
        acc = await db.rahaza_cash_accounts.find_one({"id": doc["account_id"]}, {"_id": 0})
        if acc:
            await db.rahaza_cash_movements.insert_one({
                "id": _uid(), "account_id": doc["account_id"], "account_name": acc.get("name"),
                "direction": "out", "amount": doc["amount"],
                "category": "expense", "ref_id": doc["id"], "ref_label": doc["description"][:40],
                "date": doc["date"], "notes": doc["notes"],
                "timestamp": _now(), "created_by": user["id"], "created_by_name": user.get("name", ""),
            })
            await db.rahaza_cash_accounts.update_one({"id": doc["account_id"]}, {"$inc": {"balance": -doc["amount"]}})
    # ── F2 Auto-post
    posting_result = None
    try:
        posting_result = await post_expense(db, doc, user)
    except Exception as e:
        log.exception("Expense auto-post failed")
        posting_result = {"ok": False, "error": str(e)}
    out = await db.rahaza_expenses.find_one({"id": doc["id"]}, {"_id": 0})
    out["_posting_result"] = posting_result
    return serialize_doc(out)


@router.post("/expenses/{eid}/post-to-gl")
async def retry_post_expense(eid: str, request: Request):
    """F2: manual retry post expense to GL."""
    user = await _require_fin(request)
    db = get_db()
    exp = await db.rahaza_expenses.find_one({"id": eid}, {"_id": 0})
    if not exp:
        raise HTTPException(404, "Expense tidak ditemukan.")
    result = await post_expense(db, exp, user)
    out = await db.rahaza_expenses.find_one({"id": eid}, {"_id": 0})
    out["_posting_result"] = result
    return serialize_doc(out)


@router.get("/finance-summary")
async def finance_summary(request: Request):
    """Ringkasan Finance utk dashboard."""
    await require_auth(request)
    db = get_db()
    # AR outstanding
    ar = await db.rahaza_ar_invoices.aggregate([
        {"$match": {"status": {"$in": ["sent", "issued", "partial_paid", "overdue"]}}},
        {"$group": {"_id": None, "outstanding": {"$sum": "$balance"}, "count": {"$sum": 1}}},
    ]).to_list(500)
    ap = await db.rahaza_ap_invoices.aggregate([
        {"$match": {"status": {"$in": ["sent", "partial_paid"]}}},
        {"$group": {"_id": None, "outstanding": {"$sum": "$balance"}, "count": {"$sum": 1}}},
    ]).to_list(500)
    cash_total = await db.rahaza_cash_accounts.aggregate([
        {"$match": {"active": True}},
        {"$group": {"_id": None, "balance": {"$sum": "$balance"}, "count": {"$sum": 1}}},
    ]).to_list(500)
    return {
        "ar_outstanding": round((ar[0] if ar else {}).get("outstanding", 0) or 0),
        "ar_count": (ar[0] if ar else {}).get("count", 0),
        "ap_outstanding": round((ap[0] if ap else {}).get("outstanding", 0) or 0),
        "ap_count": (ap[0] if ap else {}).get("count", 0),
        "cash_balance": round((cash_total[0] if cash_total else {}).get("balance", 0) or 0),
        "cash_accounts_count": (cash_total[0] if cash_total else {}).get("count", 0),
    }



# ══════════════════════════════════════════════════════════════════════════════
# CUSTOMER STATEMENT (rekening koran piutang) — dipindah dari rahaza_shipments
# (deprecated) ke engine AR. Hanya membaca rahaza_ar_invoices + rahaza_customers.
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/customer-statement/{customer_id}")
async def customer_statement(customer_id: str, request: Request):
    """
    Statement piutang customer dengan rentang tanggal.
    Response: {customer, period, invoices, summary:{count,total_billed,total_paid,outstanding}}
    """
    await require_auth(request)
    db = get_db()
    sp = request.query_params
    date_from = sp.get("date_from")
    date_to = sp.get("date_to")

    cust = await db.rahaza_customers.find_one({"id": customer_id}, {"_id": 0})
    if not cust:
        raise HTTPException(404, "Customer tidak ditemukan")

    q = {"customer_id": customer_id}
    if date_from and date_to:
        q["issue_date"] = {"$gte": date_from, "$lte": date_to}
    invoices = await db.rahaza_ar_invoices.find(q, {"_id": 0}).sort("issue_date", 1).to_list(500)

    total_billed = sum(float(i.get("total") or 0) for i in invoices)
    total_paid = sum(float(i.get("paid") or 0) for i in invoices)
    closing = total_billed - total_paid

    return {
        "customer": {
            "id": cust.get("id"),
            "code": cust.get("code"),
            "name": cust.get("name"),
            "address": cust.get("address"),
            "phone": cust.get("phone"),
        },
        "period": {"from": date_from, "to": date_to},
        "invoices": invoices,
        "summary": {
            "count": len(invoices),
            "total_billed": total_billed,
            "total_paid": total_paid,
            "outstanding": closing,
        },
    }
