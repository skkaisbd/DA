"""
leave_service.py — Kalkulasi Cuti dan Saldo Leave
CV. Dewi Aditya — P1 Service Layer Expansion

Fungsi:
- get_leave_balance(db, employee_id, year) → {leave_type_id: balance_info}
- calculate_duration(from_date, to_date, exclude_weekends, db) → int
- check_leave_eligibility(db, employee_id, leave_type_id, duration) → {ok, reason}
- get_pending_leaves(db, employee_id) → list[leave_doc]
"""
from typing import Optional
from datetime import datetime, timedelta
from motor.motor_asyncio import AsyncIOMotorDatabase
from utils.waktu import wib_year


async def get_leave_balance(
    db: AsyncIOMotorDatabase,
    employee_id: str,
    year: Optional[int] = None,
) -> dict:
    """
    Ambil saldo cuti per tipe untuk satu karyawan.
    Returns: {leave_type_id: {allocated, used, pending, remaining}}
    """
    yr = year or wib_year()
    balances = await db.rahaza_leave_balances.find(
        {"employee_id": employee_id, "year": yr},
        {"_id": 0}
    ).to_list(50)

    result = {}
    for b in balances:
        lt_id = b.get("leave_type_id") or b.get("leave_type", "")
        result[lt_id] = {
            "leave_type_id": lt_id,
            "allocated": float(b.get("allocated_days") or b.get("allocation") or 0),
            "used":      float(b.get("used_days") or b.get("used") or 0),
            "pending":   float(b.get("pending_days") or b.get("pending") or 0),
            "carried":   float(b.get("carried_over") or 0),
            "remaining": float(b.get("remaining_days") or b.get("remaining") or 0),
            "year":      yr,
        }
    return result


def calculate_duration(
    from_date: str,
    to_date: str,
    exclude_weekends: bool = True,
) -> int:
    """
    Hitung jumlah hari cuti (inklusif).
    exclude_weekends=True: skip Sabtu & Minggu.
    """
    try:
        d1 = datetime.strptime(from_date, "%Y-%m-%d").date()
        d2 = datetime.strptime(to_date, "%Y-%m-%d").date()
    except ValueError:
        return 0
    if d2 < d1:
        return 0
    total = 0
    curr = d1
    while curr <= d2:
        if not exclude_weekends or curr.weekday() < 5:
            total += 1
        curr += timedelta(days=1)
    return total


async def check_leave_eligibility(
    db: AsyncIOMotorDatabase,
    employee_id: str,
    leave_type_id: str,
    duration: int,
    year: Optional[int] = None,
) -> dict:
    """
    Cek apakah karyawan bisa mengambil cuti.
    Returns: {ok: bool, reason: str, available: int}
    """
    balances = await get_leave_balance(db, employee_id, year)
    if leave_type_id not in balances:
        # No quota configured → assume allowed (e.g., emergency leave)
        return {"ok": True, "reason": "", "available": 999}

    b = balances[leave_type_id]
    available = b["remaining"]
    if duration > available:
        return {
            "ok": False,
            "reason": f"Saldo tidak cukup: tersedia {available:.0f} hari, diminta {duration} hari.",
            "available": int(available),
        }

    # Check for overlapping approved/pending leaves
    pending = await db.rahaza_leave_requests.count_documents({
        "employee_id": employee_id,
        "status": {"$in": ["pending_approval", "approved", "pending_hr_approval"]},
    })
    if pending > 5:
        return {"ok": False, "reason": "Terlalu banyak cuti pending, selesaikan dulu.", "available": int(available)}

    return {"ok": True, "reason": "", "available": int(available)}


async def get_pending_leaves(
    db: AsyncIOMotorDatabase,
    employee_id: str,
) -> list:
    """Ambil semua cuti yang masih pending approval untuk karyawan."""
    return await db.rahaza_leave_requests.find(
        {"employee_id": employee_id, "status": {"$in": ["pending_approval", "pending_hr_approval"]}},
        {"_id": 0}
    ).sort("created_at", -1).to_list(20)


async def get_leave_stats(
    db: AsyncIOMotorDatabase,
    year: Optional[int] = None,
) -> dict:
    """Stats ringkasan leave untuk HR dashboard."""
    yr = year or wib_year()
    yr_str = str(yr)
    total = await db.rahaza_leave_requests.count_documents({"from_date": {"$regex": f"^{yr_str}"}})
    pending = await db.rahaza_leave_requests.count_documents({"status": {"$in": ["pending_approval", "pending_hr_approval"]}})
    approved = await db.rahaza_leave_requests.count_documents({"status": "approved", "from_date": {"$regex": f"^{yr_str}"}})
    return {"total": total, "pending": pending, "approved": approved, "year": yr}
