"""
CV. Dewi Aditya / PT Rahaza — Leave Balance Tracking (Phase 8.9 P0.3)

Per-employee annual leave quota tracking.

Collection:
  rahaza_leave_balances
    - id (UUID), employee_id, leave_type_id, year
    - allocated: default dari leave_type.quota_default, atau manual override
    - used: auto-incremented saat leave approved
    - remaining: allocated - used (computed)
    - adjustments: [{date, by, delta, reason}]
"""
# ruff: noqa: E741
import uuid
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Request, HTTPException
from database import get_db
from auth import require_auth
from utils.waktu import wib_year

router = APIRouter(prefix="/api/rahaza/leave-balances", tags=["rahaza-leave-balances"])


def _uid(): return str(uuid.uuid4())
def _now(): return datetime.now(timezone.utc)
def _s(d):
    if not d:
        return None
    d = dict(d)
    d.pop("_id", None)
    for k, v in d.items():
        if isinstance(v, datetime):
            d[k] = v.isoformat()
    return d


async def _require_admin(request: Request):
    user = await require_auth(request)
    role = user.get("role", "")
    if role not in ("superadmin", "admin", "owner", "hr", "manager"):
        raise HTTPException(403, "Hanya HR/Manager yang dapat mengelola saldo cuti.")
    return user


async def get_or_create_balance(db, employee_id: str, leave_type_id: str, year: int) -> dict:
    """Ensure balance record exists for (employee, leave_type, year)."""
    existing = await db.rahaza_leave_balances.find_one(
        {"employee_id": employee_id, "leave_type_id": leave_type_id, "year": year},
        {"_id": 0},
    )
    if existing:
        return existing

    lt = await db.rahaza_leave_types.find_one({"id": leave_type_id}, {"_id": 0})
    allocated = int(lt.get("quota_default", 12)) if lt else 12

    doc = {
        "id": _uid(),
        "employee_id": employee_id,
        "leave_type_id": leave_type_id,
        "year": year,
        "allocated": allocated,
        "used": 0,
        "adjustments": [],
        "created_at": _now(),
        "updated_at": _now(),
    }
    await db.rahaza_leave_balances.insert_one(dict(doc))
    return doc


async def consume_balance(db, employee_id: str, leave_type_id: str, year: int, days: float):
    """Deduct from balance when leave approved. Returns updated doc."""
    doc = await get_or_create_balance(db, employee_id, leave_type_id, year)
    new_used = (doc.get("used", 0) or 0) + days
    await db.rahaza_leave_balances.update_one(
        {"id": doc["id"]},
        {"$set": {"used": new_used, "updated_at": _now()}}
    )


async def restore_balance(db, employee_id: str, leave_type_id: str, year: int, days: float):
    """Restore balance (e.g., when leave is cancelled after approval)."""
    doc = await db.rahaza_leave_balances.find_one(
        {"employee_id": employee_id, "leave_type_id": leave_type_id, "year": year},
        {"_id": 0},
    )
    if doc:
        new_used = max(0, (doc.get("used", 0) or 0) - days)
        await db.rahaza_leave_balances.update_one(
            {"id": doc["id"]},
            {"$set": {"used": new_used, "updated_at": _now()}}
        )


# ─── Endpoints ───────────────────────────────────────────────────────────────

@router.get("")
async def list_balances(
    request: Request,
    employee_id: Optional[str] = None,
    year: Optional[int] = None,
    leave_type_id: Optional[str] = None,
):
    await require_auth(request)
    db = get_db()
    filt = {}
    if employee_id:
        filt["employee_id"] = employee_id
    if year:
        filt["year"] = year
    if leave_type_id:
        filt["leave_type_id"] = leave_type_id

    docs = await db.rahaza_leave_balances.find(filt, {"_id": 0}).to_list(500)

    # Enrich with employee + leave type info
    # RC-22 guard: dok schema-lama (tanpa leave_type_id) tidak boleh membuat 500
    emp_ids = list({d.get("employee_id") for d in docs if d.get("employee_id")})
    lt_ids = list({d.get("leave_type_id") for d in docs if d.get("leave_type_id")})
    emps = await db.rahaza_employees.find({"id": {"$in": emp_ids}}, {"_id": 0, "id": 1, "name": 1, "employee_code": 1}).to_list(500) if emp_ids else []
    lts = await db.rahaza_leave_types.find({"id": {"$in": lt_ids}}, {"_id": 0, "id": 1, "name": 1, "code": 1, "color": 1}).to_list(500) if lt_ids else []
    emp_map = {e["id"]: e for e in emps}
    lt_map = {l["id"]: l for l in lts}

    result = []
    for d in docs:
        d2 = _s(d)
        d2["remaining"] = d2.get("allocated", 0) - d2.get("used", 0)
        d2["employee"] = emp_map.get(d2.get("employee_id"))
        d2["leave_type"] = lt_map.get(d2.get("leave_type_id"))
        result.append(d2)

    return {"ok": True, "balances": result}


@router.get("/my")
async def my_balances(request: Request, year: Optional[int] = None):
    """Saldo cuti milik karyawan yang login.

    BUG-4 (2026-07-26): dulu memakai `user.get("employee_id")` MENTAH dari JWT.
    Token berlaku 24 jam, jadi karyawan yang baru ditautkan HR hari itu tetap
    mendapat 409 "User belum ter-link ke karyawan. Hubungi HR." sampai ia login
    ulang — persis keluhan "error setup cuti karyawan". Sekarang memakai SSOT
    `utils/employee_identity.resolve_my_employee` (employee_id → user_id → email).
    """
    user = await require_auth(request)
    db = get_db()
    from utils.employee_identity import resolve_my_employee
    emp = await resolve_my_employee(db, user)
    if not emp:
        raise HTTPException(
            409,
            "Akun Anda belum ditautkan ke data karyawan. Minta Admin HR menautkan "
            "lewat menu Data Karyawan → Tautkan Akun.")
    emp_id = emp["id"]
    target_year = year or wib_year()
    filt = {"employee_id": emp_id, "year": target_year}
    docs = await db.rahaza_leave_balances.find(filt, {"_id": 0}).to_list(500)

    lt_ids = [d["leave_type_id"] for d in docs]
    # Also include leave types the employee hasn't used yet (for completeness)
    all_lts = await db.rahaza_leave_types.find({"active": True}, {"_id": 0}).to_list(500)
    lt_map = {l["id"]: l for l in all_lts}
    existing_lt_ids = set(lt_ids)

    # Auto-create missing balances
    for lt in all_lts:
        if lt["id"] not in existing_lt_ids:
            nd = await get_or_create_balance(db, emp_id, lt["id"], target_year)
            docs.append(nd)

    result = []
    for d in docs:
        d2 = _s(d)
        d2["remaining"] = d2.get("allocated", 0) - d2.get("used", 0)
        d2["leave_type"] = lt_map.get(d2["leave_type_id"])
        result.append(d2)
    return {"ok": True, "year": target_year, "balances": result}


@router.post("/allocate-year")
async def allocate_year(request: Request):
    """Admin: bulk allocate annual quota for all active employees, for all leave types."""
    await _require_admin(request)
    db = get_db()
    body = await request.json()
    year = int(body.get("year") or wib_year())
    force_reset = bool(body.get("force_reset", False))
    if not (2000 <= year <= 2100):
        raise HTTPException(400, "Tahun tidak masuk akal (2000–2100).")

    # BUG-4: filter `{"active": True}` MELEWATKAN karyawan lama yang dokumennya
    # belum punya field `active` sama sekali ⇒ mereka tidak pernah dapat jatah
    # cuti dan HR mengira "setup cuti"-nya gagal. Pakai filter SSOT.
    from utils.employee_identity import ACTIVE_EMPLOYEE_FILTER
    employees = await db.rahaza_employees.find(
        dict(ACTIVE_EMPLOYEE_FILTER), {"_id": 0, "id": 1}).to_list(2000)
    leave_types = await db.rahaza_leave_types.find({"active": True}, {"_id": 0, "id": 1, "quota_default": 1}).to_list(500)
    if not employees or not leave_types:
        raise HTTPException(
            409,
            "Belum ada karyawan aktif atau jenis cuti aktif — tidak ada yang bisa "
            "dialokasikan. Isi Data Karyawan / Master Tipe Cuti dulu.")

    created = 0
    updated = 0
    for emp in employees:
        for lt in leave_types:
            existing = await db.rahaza_leave_balances.find_one(
                {"employee_id": emp["id"], "leave_type_id": lt["id"], "year": year}
            )
            if existing and not force_reset:
                continue
            allocated = int(lt.get("quota_default", 12))
            if existing:
                await db.rahaza_leave_balances.update_one(
                    {"id": existing["id"]},
                    {"$set": {"allocated": allocated, "used": 0, "updated_at": _now()}}
                )
                updated += 1
            else:
                doc = {
                    "id": _uid(),
                    "employee_id": emp["id"],
                    "leave_type_id": lt["id"],
                    "year": year,
                    "allocated": allocated,
                    "used": 0,
                    "adjustments": [],
                    "created_at": _now(),
                    "updated_at": _now(),
                }
                await db.rahaza_leave_balances.insert_one(doc)
                created += 1

    return {"ok": True, "year": year, "created": created, "updated": updated,
            "total_employees": len(employees), "total_leave_types": len(leave_types)}


@router.put("/{balance_id}")
async def update_balance(balance_id: str, request: Request):
    """Admin manual adjust: set new allocated, or add/subtract via adjustment."""
    user = await _require_admin(request)
    db = get_db()
    body = await request.json()

    doc = await db.rahaza_leave_balances.find_one({"id": balance_id}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Balance tidak ditemukan.")

    upd = {"updated_at": _now()}

    # BUG-4: `int(body["allocated"])` melempar ValueError → HTTP 500 polos ketika
    # HR mengetik teks/kosong di kolom jatah. Sekarang 400 dengan pesan jelas.
    def _num(key: str, cast, lo: float, hi: float):
        try:
            v = cast(body[key])
        except (TypeError, ValueError):
            raise HTTPException(400, f"Nilai '{key}' harus berupa angka.")
        if not (lo <= v <= hi):
            raise HTTPException(400, f"Nilai '{key}' harus antara {lo:g} dan {hi:g}.")
        return v

    if "allocated" in body:
        upd["allocated"] = _num("allocated", int, 0, 365)
    if "used" in body:
        upd["used"] = _num("used", float, 0, 365)

    # Adjustment log
    if "adjust_delta" in body:
        delta = _num("adjust_delta", float, -365, 365)
        new_alloc = (doc.get("allocated", 0) or 0) + delta
        if new_alloc < 0:
            raise HTTPException(
                400, f"Penyesuaian membuat jatah menjadi {new_alloc:g} hari (negatif). "
                     "Kurangi nilai penyesuaian.")
        upd["allocated"] = new_alloc
        adj = {
            "date": _now().isoformat(),
            "by": user.get("name", ""),
            "by_id": user["id"],
            "delta": delta,
            "reason": body.get("reason", ""),
        }
        upd["adjustments"] = (doc.get("adjustments") or []) + [adj]

    await db.rahaza_leave_balances.update_one({"id": balance_id}, {"$set": upd})
    out = await db.rahaza_leave_balances.find_one({"id": balance_id}, {"_id": 0})
    return {"ok": True, "balance": _s(out)}
