"""
PT Rahaza — Phase F1 Accounting Core
Fiscal Periods (month-based). status: open | closed | locked.
Closed = no new posting; Locked = no open/close anymore (final audit lock, admin only).

Collection: rahaza_periods
  id, period_code (YYYY-MM), period_label, year, month,
  status, closed_at, closed_by, locked_at, locked_by
"""
from fastapi import APIRouter, Request, HTTPException
from database import get_db
from auth import require_auth, serialize_doc, log_activity
import uuid
from datetime import datetime, timezone, date

router = APIRouter(prefix="/api/rahaza/periods", tags=["rahaza-periods"])


def _uid(): return str(uuid.uuid4())
def _now(): return datetime.now(timezone.utc)


async def _require_fin_mgr(request: Request):
    user = await require_auth(request)
    role = (user.get("role") or "").lower()
    if role in ("superadmin", "admin", "owner", "accounting", "finance"):
        return user
    perms = user.get("_permissions") or []
    if "*" in perms or "finance.manage" in perms:
        return user
    raise HTTPException(403, "Forbidden: butuh role finance/accounting.")


@router.get("")
async def list_periods(request: Request, year: int = 0):
    await require_auth(request)
    db = get_db()
    q = {}
    if year:
        q["year"] = year
    rows = await db.rahaza_periods.find(q, {"_id": 0}).sort("period_code", -1).to_list(500)
    return serialize_doc(rows)


@router.post("/ensure-year")
async def ensure_year(request: Request):
    """Create 12 monthly periods for given year (idempotent)."""
    user = await _require_fin_mgr(request)
    db = get_db()
    try:
        body = await request.json()
    except Exception:
        body = {}
    year = int((body or {}).get("year") or date.today().year)
    created = 0
    # Batch fetch existing period codes
    target_codes = [f"{year}-{m:02d}" for m in range(1, 13)]
    existing_codes = set()
    async for d in db.rahaza_periods.find(
        {"period_code": {"$in": target_codes}}, {"_id": 0, "period_code": 1}
    ):
        existing_codes.add(d["period_code"])
    for m in range(1, 13):
        code = f"{year}-{m:02d}"
        if code in existing_codes:
            continue
        label = date(year, m, 1).strftime("%B %Y")
        doc = {
            "id": _uid(),
            "period_code": code,
            "period_label": label,
            "year": year,
            "month": m,
            "status": "open",
            "closed_at": None,
            "closed_by": None,
            "locked_at": None,
            "locked_by": None,
            "created_at": _now(),
        }
        await db.rahaza_periods.insert_one(doc)
        created += 1
    await log_activity(user["id"], user.get("name", ""), "ensure_periods", "periods", f"year={year} created={created}")
    return {"ok": True, "year": year, "created": created}


@router.post("/{period_code}/close")
async def close_period(period_code: str, request: Request):
    user = await _require_fin_mgr(request)
    db = get_db()
    per = await db.rahaza_periods.find_one({"period_code": period_code})
    if not per:
        raise HTTPException(404, "Periode tidak ditemukan.")
    if per["status"] in ("closed", "locked"):
        raise HTTPException(400, f"Periode sudah {per['status']}.")
    # check draft journals in this period: warn but allow
    drafts = await db.rahaza_journal_entries.count_documents({"date": {"$regex": f"^{period_code}"}, "status": "draft"})
    await db.rahaza_periods.update_one(
        {"period_code": period_code},
        {"$set": {"status": "closed", "closed_at": _now(), "closed_by": user["id"], "closed_by_name": user.get("name", "")}},
    )
    await log_activity(user["id"], user.get("name", ""), "close_period", "periods", period_code)
    return {"ok": True, "period_code": period_code, "status": "closed", "draft_journals_left": drafts}


@router.post("/{period_code}/reopen")
async def reopen_period(period_code: str, request: Request):
    user = await _require_fin_mgr(request)
    db = get_db()
    per = await db.rahaza_periods.find_one({"period_code": period_code})
    if not per:
        raise HTTPException(404, "Periode tidak ditemukan.")
    if per["status"] == "locked":
        raise HTTPException(423, "Periode terkunci (locked) dan tidak bisa di-reopen.")
    if per["status"] != "closed":
        raise HTTPException(400, f"Hanya periode closed yang bisa reopen. Status sekarang: {per['status']}")
    await db.rahaza_periods.update_one(
        {"period_code": period_code},
        {"$set": {"status": "open", "closed_at": None, "closed_by": None}},
    )
    await log_activity(user["id"], user.get("name", ""), "reopen_period", "periods", period_code)
    return {"ok": True, "period_code": period_code, "status": "open"}


@router.post("/{period_code}/lock")
async def lock_period(period_code: str, request: Request):
    """Final lock (audit). Only admin/superadmin."""
    user = await require_auth(request)
    if (user.get("role") or "").lower() not in ("superadmin", "admin", "owner"):
        raise HTTPException(403, "Hanya admin/superadmin yang boleh lock periode.")
    db = get_db()
    per = await db.rahaza_periods.find_one({"period_code": period_code})
    if not per:
        raise HTTPException(404, "Periode tidak ditemukan.")
    if per["status"] == "locked":
        raise HTTPException(400, "Periode sudah locked.")
    if per["status"] != "closed":
        raise HTTPException(400, "Hanya periode closed yang bisa di-lock.")
    await db.rahaza_periods.update_one(
        {"period_code": period_code},
        {"$set": {"status": "locked", "locked_at": _now(), "locked_by": user["id"], "locked_by_name": user.get("name", "")}},
    )
    await log_activity(user["id"], user.get("name", ""), "lock_period", "periods", period_code)
    return {"ok": True, "period_code": period_code, "status": "locked"}
